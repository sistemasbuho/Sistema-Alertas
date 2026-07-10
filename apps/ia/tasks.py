import logging
from datetime import timedelta

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

ESTADOS_CLASIFICABLES = ["pendiente_ia", "clasificando"]


@shared_task(name="ia.ping")
def ping():
    """Tarea de humo para verificar broker/worker."""
    return "pong"


@shared_task(
    name="ia.clasificar_alerta",
    bind=True,
    soft_time_limit=None,  # se fija en runtime vía settings al aplicar
    max_retries=2,
)
def clasificar_alerta(self, detalle_envio_id):
    """Clasifica una alerta con IA y aplica el gate. Idempotente: usa un
    compare-and-set atómico sobre estado_pipeline para tolerar re-ejecuciones."""
    from apps.base.models import DetalleEnvio
    from apps.ia.services import clasificador

    # CAS: solo un worker toma la alerta; 0 filas = ya la tomó otro / ya resuelta
    tomadas = DetalleEnvio.objects.filter(
        id=detalle_envio_id, estado_pipeline__in=ESTADOS_CLASIFICABLES
    ).update(
        estado_pipeline=DetalleEnvio.PIPELINE_CLASIFICANDO,
        intentos_ia=F("intentos_ia") + 1,
    )
    if not tomadas:
        return "omitida"

    detalle = (
        DetalleEnvio.objects.select_related(
            "proyecto", "red_social__red_social", "medio", "proyecto"
        )
        .filter(id=detalle_envio_id)
        .first()
    )
    if detalle is None:
        return "no_existe"

    matriz = getattr(detalle.proyecto, "matriz_ia", None)
    if matriz is None or not matriz.activo:
        # El proyecto dejó de tener pipeline IA: vuelve al flujo manual
        detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_MANUAL)
        return "sin_matriz"

    from apps.ia.models import EvaluacionIA

    try:
        evaluacion = clasificador.clasificar_detalle(detalle, matriz)
    except SoftTimeLimitExceeded:
        clasificador.registrar_fallback(
            detalle,
            matriz,
            motivo="Timeout de clasificación IA",
            decision_por=EvaluacionIA.POR_TIMEOUT,
        )
        return "timeout"
    except Exception as exc:  # pylint: disable=broad-except
        # B3: la inmediatez gana — sin reintentos largos, el error cae a cola
        # humana de una vez (el sweeper cubre cualquier otro atasco).
        logger.exception("Clasificación IA falló para %s", detalle_envio_id)
        clasificador.registrar_fallback(
            detalle,
            matriz,
            motivo=f"Error de clasificación IA: {exc}",
            decision_por=EvaluacionIA.POR_ERROR,
        )
        return "error"

    if evaluacion is None:
        return "sin_alerta"

    # Encadenar según el estado resultante
    detalle.refresh_from_db()
    if detalle.estado_pipeline == DetalleEnvio.PIPELINE_AUTO_APROBADA:
        from apps.whatsapp.tasks import enviar_alerta

        enviar_alerta.delay(str(detalle.id))
    elif detalle.estado_pipeline == DetalleEnvio.PIPELINE_ENRIQUECIENDO:
        completar_datos.delay(str(detalle.id))

    return detalle.estado_pipeline


@shared_task(name="ia.reevaluar_tras_enriquecimiento", bind=True, max_retries=1)
def reevaluar_tras_enriquecimiento(self, detalle_envio_id):
    """Tras completar datos, re-pasa el gate SIN nueva llamada al LLM
    (recalcula semáforo/datos faltantes con la última evaluación)."""
    from apps.base.models import DetalleEnvio
    from apps.ia.models import EvaluacionIA
    from apps.ia.services.clasificador import _alerta_dict
    from apps.ia.services.gate import decidir

    detalle = (
        DetalleEnvio.objects.select_related("proyecto", "red_social__red_social", "medio")
        .filter(id=detalle_envio_id)
        .first()
    )
    if detalle is None or detalle.estado_pipeline != DetalleEnvio.PIPELINE_ENRIQUECIENDO:
        return "omitida"

    matriz = getattr(detalle.proyecto, "matriz_ia", None)
    evaluacion = detalle.evaluaciones_ia.order_by("-created_at").first()
    if matriz is None or evaluacion is None or evaluacion.respuesta_cruda is None:
        detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_COLA_EXCEPCIONES)
        return "cola_sin_contexto"

    alerta, tipo_alerta = _alerta_dict(detalle)
    decision = decidir(
        matriz=matriz,
        detalle=detalle,
        salida=evaluacion.respuesta_cruda,
        tipo_alerta=tipo_alerta,
        alerta=alerta,
    )

    # Si sigue faltando data tras enriquecer, va a cola humana (no otro ciclo)
    estado = decision["estado_pipeline"]
    if estado == DetalleEnvio.PIPELINE_ENRIQUECIENDO:
        estado = DetalleEnvio.PIPELINE_COLA_EXCEPCIONES
        decision["decision"] = EvaluacionIA.DECISION_COLA

    evaluacion.decision = decision["decision"]
    evaluacion.riesgo = decision["riesgo"]
    evaluacion.riesgo_detalle = decision["riesgo_detalle"]
    evaluacion.datos_faltantes = decision["datos_faltantes"]
    evaluacion.confianza_global = decision["confianza"]
    evaluacion.save()

    detalle.aplicar_estado_pipeline(estado)
    if estado == DetalleEnvio.PIPELINE_AUTO_APROBADA:
        from apps.whatsapp.tasks import enviar_alerta

        enviar_alerta.delay(str(detalle.id))
    return estado


@shared_task(name="enriquecimiento.completar_datos", soft_time_limit=300)
def completar_datos(detalle_envio_id):
    """Completado de datos faltantes (Epic C): corre en la cola `enrich` y al
    terminar reencola la reevaluación del gate en la cola `fast`. Cualquier
    fallo NO bloquea: la reevaluación decide con lo que haya."""
    from apps.base.models import DetalleEnvio
    from apps.ia.services.enriquecimiento import orchestrator

    detalle = (
        DetalleEnvio.objects.select_related("red_social__red_social", "medio")
        .filter(id=detalle_envio_id)
        .first()
    )
    if detalle is None or detalle.estado_pipeline != DetalleEnvio.PIPELINE_ENRIQUECIENDO:
        return "omitida"

    completados = []
    try:
        evaluacion = detalle.evaluaciones_ia.order_by("-created_at").first()
        faltantes = (evaluacion.datos_faltantes if evaluacion else None) or []
        completados = orchestrator.completar(detalle, faltantes)
        if evaluacion and completados:
            evaluacion.datos_completados = (evaluacion.datos_completados or []) + completados
            evaluacion.save()
    except SoftTimeLimitExceeded:
        logger.warning("Enriquecimiento excedió el tiempo para %s", detalle_envio_id)
    except Exception:  # pylint: disable=broad-except
        logger.exception("Enriquecimiento falló para %s", detalle_envio_id)

    reevaluar_tras_enriquecimiento.delay(detalle_envio_id)
    return {"completados": len(completados)}


@shared_task(name="ia.rescatar_alertas_atascadas")
def rescatar_alertas_atascadas():
    """Sweeper B3 (beat cada 60s): cualquier alerta atascada en el pipeline
    pasa a cola humana. La inmediatez gana sobre la automatización."""
    from apps.base.models import DetalleEnvio
    from apps.ia.models import EvaluacionIA
    from apps.ia.services import clasificador

    ahora = timezone.now()
    limite_ia = ahora - timedelta(seconds=settings.IA_TIMEOUT_TOTAL)
    limite_enr = ahora - timedelta(seconds=settings.ENRIQUECIMIENTO_TIMEOUT)

    atascadas = DetalleEnvio.objects.select_related("proyecto").filter(
        Q(
            estado_pipeline__in=[
                DetalleEnvio.PIPELINE_PENDIENTE_IA,
                DetalleEnvio.PIPELINE_CLASIFICANDO,
            ],
            modified_at__lt=limite_ia,
        )
        | Q(estado_pipeline=DetalleEnvio.PIPELINE_ENRIQUECIENDO, modified_at__lt=limite_enr)
    )

    rescatadas = 0
    for detalle in atascadas:
        matriz = getattr(detalle.proyecto, "matriz_ia", None)
        clasificador.registrar_fallback(
            detalle,
            matriz,
            motivo=f"Alerta atascada en '{detalle.estado_pipeline}' — rescatada por sweeper",
            decision_por=EvaluacionIA.POR_TIMEOUT,
        )
        rescatadas += 1

    if rescatadas:
        logger.warning("Sweeper: %s alertas movidas a cola de excepciones", rescatadas)
    return rescatadas
