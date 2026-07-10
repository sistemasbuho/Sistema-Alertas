import os

import requests

from .base import MensajeriaProvider, ResultadoEnvio

URL_MENSAJE = "https://gate.whapi.cloud/messages/text"

_NO_PROVISTO = object()


class WhapiProvider(MensajeriaProvider):
    """Proveedor actual (WHAPI). El request es idéntico al del flujo legacy
    de enviar_mensaje.py: mismo endpoint, payload y headers."""

    nombre = "whapi"

    def __init__(self, token=_NO_PROVISTO):
        self.token = os.getenv("WHAPI_TOKEN") if token is _NO_PROVISTO else token

    def disponible(self):
        return bool(self.token)

    def send_text(self, grupo_id, body, no_link_preview=True):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload = {"to": grupo_id, "body": body, "no_link_preview": no_link_preview}
        try:
            response = requests.post(URL_MENSAJE, json=payload, headers=headers)
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
            exito=response.status_code == 200,
            proveedor=self.nombre,
            status_code=response.status_code,
            detalle=detalle,
        )
