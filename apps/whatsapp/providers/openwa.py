import os

import requests
from django.conf import settings

from .base import MensajeriaProvider, ResultadoEnvio


class OpenWAProvider(MensajeriaProvider):
    """Proveedor fallback autohospedado (https://github.com/rmyndharis/OpenWA).

    SPIKE PENDIENTE: la ruta de envío y el formato de JID de grupo deben
    validarse contra una instancia real (ver fase de spike del sprint). El
    proveedor queda deshabilitado mientras OPENWA_BASE_URL no esté configurada,
    por lo que nunca participa de la cadena en producción.
    """

    nombre = "openwa"

    def __init__(self, base_url=None, api_key=None):
        self.base_url = (
            base_url
            if base_url is not None
            else getattr(settings, "OPENWA_BASE_URL", None) or os.getenv("OPENWA_BASE_URL")
        )
        self.api_key = (
            api_key
            if api_key is not None
            else getattr(settings, "OPENWA_API_KEY", None) or os.getenv("OPENWA_API_KEY")
        )
        self.session = os.getenv("OPENWA_SESSION", "default")
        self.send_path = os.getenv("OPENWA_SEND_PATH", "/api/sendText")

    def disponible(self):
        return bool(self.base_url)

    def send_text(self, grupo_id, body, no_link_preview=True):
        url = f"{self.base_url.rstrip('/')}{self.send_path}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        payload = {"chatId": grupo_id, "text": body, "session": self.session}
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
        except requests.RequestException as exc:
            return ResultadoEnvio(
                exito=False,
                proveedor=self.nombre,
                detalle=f"Error de conexión: {exc}",
            )

        try:
            detalle = response.json()
        except ValueError:
            detalle = response.text

        return ResultadoEnvio(
            exito=200 <= response.status_code < 300,
            proveedor=self.nombre,
            status_code=response.status_code,
            detalle=detalle,
        )
