from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.base.models import DetalleEnvio
from apps.ia.models import EvaluacionIA

ACCIONES = ("confirmar", "corregir", "descartar")

# Campos de clasificación corregibles y campos de la alerta editables
CAMPOS_CORRECCION = ("relevante", "tonalidad", "categoria_sector", "pais", "semaforo")
CAMPOS_ALERTA = (
    "titulo",
    "contenido",
    "url",
    "autor",
    "ubicacion",
    "fecha_publicacion",
    "reach",
    "engagement",
)


def _resolver_una(detalle, *, accion, correccion, campos, motivo, enviar, usuario):
    """Resuelve una alerta de la cola. Devuelve (ok, payload/mensaje)."""
    if detalle.estado_pipeline != DetalleEnvio.PIPELINE_COLA_EXCEPCIONES:
        return False, "La alerta ya fue resuelta"

    evaluacion = detalle.evaluaciones_ia.order_by("-created_at").first()
    objeto = detalle.red_social or detalle.medio

    # Aplicar ediciones de campos de la alerta
    campos_aplicados = {}
    if campos and objeto is not None:
        for campo, valor in campos.items():
            if campo in CAMPOS_ALERTA and hasattr(objeto, campo):
                campos_aplicados[campo] = {
                    "antes": getattr(objeto, campo),
                    "despues": valor,
                }
                setattr(objeto, campo, valor)
        if campos_aplicados:
            objeto.save()

    if evaluacion:
        if accion == "confirmar":
            evaluacion.revision_humana = EvaluacionIA.REVISION_CONFIRMADA
        elif accion == "corregir":
            evaluacion.revision_humana = EvaluacionIA.REVISION_CORREGIDA
        else:
            evaluacion.revision_humana = EvaluacionIA.REVISION_RECHAZADA

        # Diff server-side contra lo que dijo la IA (auditoría confiable)
        diff = {}
        for campo, valor in (correccion or {}).items():
            if campo not in CAMPOS_CORRECCION:
                continue
            previo = {
                "relevante": evaluacion.relevante,
                "tonalidad": evaluacion.tonalidad,
                "categoria_sector": evaluacion.categoria_sector,
                "pais": evaluacion.pais_detectado,
                "semaforo": evaluacion.riesgo,
            }.get(campo)
            if valor != previo:
                diff[campo] = valor
        if campos_aplicados:
            diff["campos"] = {
                k: v["despues"] for k, v in campos_aplicados.items()
            }
        evaluacion.correccion = diff or None
        evaluacion.revisado_por = usuario if getattr(usuario, "is_authenticated", False) else None
        evaluacion.revisado_en = timezone.now()
        if motivo:
            evaluacion.comentario_revision = motivo
        evaluacion.save()

    if accion == "descartar":
        detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_DESCARTADA_HUMANA)
        return True, {"estado_pipeline": detalle.estado_pipeline, "envio": None}

    detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_APROBADA_HUMANA)

    envio = None
    if enviar:
        from apps.whatsapp.tasks import enviar_alerta

        transaction.on_commit(lambda: enviar_alerta.delay(str(detalle.id)))
        envio = {"encolado": True}

    return True, {"estado_pipeline": detalle.estado_pipeline, "envio": envio}


class ResolverExcepcionAPIView(APIView):
    """POST /api/ia/cola-excepciones/<detalle_id>/resolver/
    body: {accion, enviar, correccion?, campos?, motivo?}"""

    def post(self, request, detalle_id):
        accion = request.data.get("accion")
        if accion not in ACCIONES:
            return Response(
                {"error": f"'accion' debe ser una de {ACCIONES}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            detalle = (
                DetalleEnvio.objects.select_for_update()
                .select_related("proyecto", "red_social", "medio")
                .filter(id=detalle_id)
                .first()
            )
            if detalle is None:
                return Response({"error": "No existe"}, status=status.HTTP_404_NOT_FOUND)

            ok, resultado = _resolver_una(
                detalle,
                accion=accion,
                correccion=request.data.get("correccion"),
                campos=request.data.get("campos"),
                motivo=request.data.get("motivo"),
                enviar=bool(request.data.get("enviar")),
                usuario=request.user,
            )

        if not ok:
            return Response({"error": resultado}, status=status.HTTP_409_CONFLICT)
        return Response({"success": True, **resultado})


class ResolverExcepcionesBulkAPIView(APIView):
    """POST /api/ia/cola-excepciones/resolver-bulk/
    body: {ids: [], accion: confirmar|descartar, enviar: bool}"""

    def post(self, request):
        ids = request.data.get("ids") or []
        accion = request.data.get("accion")
        if accion not in ("confirmar", "descartar"):
            return Response(
                {"error": "'accion' debe ser 'confirmar' o 'descartar'"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not ids:
            return Response({"error": "'ids' es requerido"}, status=status.HTTP_400_BAD_REQUEST)

        detalles = list(
            DetalleEnvio.objects.select_related("proyecto").filter(id__in=ids)
        )
        proyectos = {d.proyecto_id for d in detalles}
        if len(proyectos) > 1:
            return Response(
                {"error": "Todas las alertas deben pertenecer al mismo proyecto"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        procesadas, fallidas = [], []
        for detalle in detalles:
            with transaction.atomic():
                detalle_bloqueado = (
                    DetalleEnvio.objects.select_for_update()
                    .select_related("red_social", "medio")
                    .get(id=detalle.id)
                )
                ok, resultado = _resolver_una(
                    detalle_bloqueado,
                    accion=accion,
                    correccion=None,
                    campos=None,
                    motivo=request.data.get("motivo"),
                    enviar=bool(request.data.get("enviar")),
                    usuario=request.user,
                )
            if ok:
                procesadas.append(str(detalle.id))
            else:
                fallidas.append({"id": str(detalle.id), "error": resultado})

        encontrados = {str(d.id) for d in detalles}
        for faltante in set(map(str, ids)) - encontrados:
            fallidas.append({"id": faltante, "error": "No existe"})

        return Response(
            {
                "success": not fallidas,
                "message": f"{len(procesadas)} alertas procesadas",
                "procesadas": procesadas,
                "fallidas": fallidas,
            }
        )
