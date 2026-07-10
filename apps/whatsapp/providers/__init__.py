"""Cadena de proveedores de mensajería WhatsApp (primario → fallback).

El orden se controla con la variable de entorno WHATSAPP_PROVIDERS
(ej. "whapi" hoy, "whapi,openwa" cuando pase el spike, invertible sin código).
"""

from django.conf import settings

from .base import MensajeriaProvider, ResultadoEnvio
from .openwa import OpenWAProvider
from .whapi import WhapiProvider

_REGISTRO = {
    WhapiProvider.nombre: WhapiProvider,
    OpenWAProvider.nombre: OpenWAProvider,
}


def get_provider_chain():
    """Proveedores configurados y disponibles, en orden de prioridad."""
    proveedores = []
    for nombre in getattr(settings, "WHATSAPP_PROVIDERS", ["whapi"]):
        clase = _REGISTRO.get(nombre)
        if clase is None:
            continue
        provider = clase()
        if provider.disponible():
            proveedores.append(provider)
    return proveedores


def enviar_texto(grupo_id, body, no_link_preview=True):
    """Envía por la cadena; devuelve el primer éxito o el último fallo."""
    resultado = None
    for provider in get_provider_chain():
        resultado = provider.send_text(grupo_id, body, no_link_preview=no_link_preview)
        if resultado.exito:
            return resultado
    return resultado or ResultadoEnvio(
        exito=False, proveedor="ninguno", detalle="Sin proveedores de mensajería configurados"
    )
