"""Envío de una alerta individual del pipeline IA (D3/D5).

Reutiliza formatear_mensaje y el mecanismo `emojis` existente para inyectar
bandera de país, semáforo de riesgo y emoji de sector sin tocar plantillas.
Envía por la cadena de proveedores (WHAPI hoy, OpenWA como fallback futuro).
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.base.models import DetalleEnvio, TemplateConfig
from apps.ia.services import reglas
from apps.whatsapp.providers import enviar_texto

logger = logging.getLogger(__name__)

ESTADOS_ENVIABLES = [
    DetalleEnvio.PIPELINE_AUTO_APROBADA,
    DetalleEnvio.PIPELINE_APROBADA_HUMANA,
]


def componer_emojis(matriz, evaluacion):
    """Bandera + semáforo + emoji de sector según matriz y evaluación vigente
    (con la corrección humana ganando sobre lo detectado por la IA)."""
    if evaluacion is None or matriz is None:
        return None

    correccion = evaluacion.correccion or {}
    partes = []

    if matriz.incluir_bandera:
        pais = correccion.get("pais") or evaluacion.pais_detectado
        emoji = reglas.bandera(pais)
        if emoji:
            partes.append(emoji)

    if matriz.incluir_semaforo and evaluacion.riesgo:
        riesgo = correccion.get("semaforo") or evaluacion.riesgo
        emojis_cfg = (matriz.config_semaforo or {}).get("emojis") or {}
        emoji = emojis_cfg.get(riesgo)
        if emoji:
            partes.append(emoji)

    categoria = correccion.get("categoria_sector") or evaluacion.categoria_sector
    if categoria:
        for criterio in matriz.criterios_sector or []:
            if criterio.get("clave") == categoria and criterio.get("emoji"):
                partes.append(criterio["emoji"])
                break

    return " ".join(partes) if partes else None


def enviar_detalle(detalle_envio_id):
    """Envía la alerta de un DetalleEnvio aprobado. Idempotente: re-verifica
    estado bajo lock antes de enviar (mismo contrato de dedup del flujo legacy).
    """
    from apps.whatsapp.api.enviar_mensaje import (
        enviar_alertas_a_monitoreo,
        formatear_mensaje,
    )

    with transaction.atomic():
        detalle = (
            DetalleEnvio.objects.select_for_update(of=("self",))
            .select_related("proyecto", "red_social__red_social", "medio")
            .filter(id=detalle_envio_id)
            .first()
        )
        if detalle is None:
            return "no_existe"
        if detalle.estado_enviado or detalle.estado_pipeline not in ESTADOS_ENVIABLES:
            return "omitida"

        proyecto = detalle.proyecto
        objeto = detalle.red_social or detalle.medio
        if objeto is None or proyecto is None:
            return "sin_alerta"

        tipo_alerta = "redes" if detalle.red_social_id else "medios"
        matriz = getattr(proyecto, "matriz_ia", None)
        evaluacion = detalle.evaluaciones_ia.order_by("-created_at").first()

        template_config = TemplateConfig.objects.filter(proyecto=proyecto).first()
        plantilla = template_config.config_campos if template_config else {}
        plantilla_nombre = template_config.nombre if template_config else None
        keywords = proyecto.get_keywords_list() if hasattr(proyecto, "get_keywords_list") else []

        fecha = objeto.fecha_publicacion
        alerta_data = {
            "url": objeto.url,
            "titulo": getattr(objeto, "titulo", None),
            "contenido": objeto.contenido,
            "autor": objeto.autor,
            "fecha_publicacion": (
                timezone.localtime(fecha).strftime("%Y-%m-%d %I:%M:%S %p") if fecha else ""
            ),
            "reach": objeto.reach,
            "engagement": objeto.engagement,
            "ubicacion": objeto.ubicacion,
            "emojis": componer_emojis(matriz, evaluacion),
        }
        mensaje = formatear_mensaje(
            alerta_data,
            plantilla,
            nombre_plantilla=plantilla_nombre,
            tipo_alerta=tipo_alerta,
            keywords=keywords,
        )

        detalle.inicio_envio = timezone.now()
        detalle.mensaje = mensaje
        detalle.save()

    resultado = enviar_texto(proyecto.codigo_acceso, mensaje)

    if resultado.exito:
        detalle.proveedor_envio = resultado.proveedor
        detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_ENVIADA)
    else:
        detalle.proveedor_envio = resultado.proveedor
        detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_ERROR_ENVIO)
        logger.error(
            "Envío fallido para %s vía %s: %s",
            detalle_envio_id,
            resultado.proveedor,
            resultado.detalle,
        )
        return "error_envio"

    # Paridad con el flujo legacy: reporte a monitoreo
    alerta_id = str(objeto.id)
    try:
        enviar_alertas_a_monitoreo(
            proyecto_id=str(proyecto.id),
            tipo_alerta=tipo_alerta,
            data_alertas={"alertas": [{**alerta_data, "id": alerta_id, "mensaje": mensaje}]},
            enviados_ids=[alerta_id],
            grupo_id=proyecto.codigo_acceso,
        )
    except Exception:  # pylint: disable=broad-except
        logger.exception("Fallo reportando a monitoreo el envío %s", detalle_envio_id)

    return "enviada"
