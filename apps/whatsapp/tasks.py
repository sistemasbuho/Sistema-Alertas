import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="whatsapp.enviar_lote_legacy", bind=True, max_retries=1)
def enviar_lote_legacy(self, proyecto_id, tipo_alerta, alertas, usuario_id=None):
    """Envuelve el envío automático legacy para sacarlo del request HTTP de
    ingesta (comportamiento idéntico, ahora asíncrono)."""
    from apps.whatsapp.api.enviar_mensaje import enviar_alertas_automatico

    kwargs = {}
    if usuario_id:
        kwargs["usuario_id"] = usuario_id
    try:
        return enviar_alertas_automatico(proyecto_id, tipo_alerta, alertas, **kwargs)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Fallo en envío legacy del proyecto %s", proyecto_id)
        raise self.retry(exc=exc, countdown=5)


@shared_task(name="whatsapp.enviar_alerta", bind=True, max_retries=3)
def enviar_alerta(self, detalle_envio_id):
    """Envía una alerta auto-aprobada (o aprobada por humano) por la cadena de
    proveedores WhatsApp, con dedup e idempotencia."""
    from apps.whatsapp.services.envio import enviar_detalle

    try:
        return enviar_detalle(detalle_envio_id)
    except Exception as exc:  # pylint: disable=broad-except
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 * (self.request.retries + 1))
        logger.exception("Envío falló definitivamente para %s", detalle_envio_id)
        from apps.base.models import DetalleEnvio

        detalle = DetalleEnvio.objects.filter(id=detalle_envio_id).first()
        if detalle:
            detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_ERROR_ENVIO)
        return "error"
