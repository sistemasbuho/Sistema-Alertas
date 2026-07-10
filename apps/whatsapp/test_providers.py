from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.whatsapp.providers import enviar_texto, get_provider_chain
from apps.whatsapp.providers.base import ResultadoEnvio
from apps.whatsapp.providers.whapi import URL_MENSAJE, WhapiProvider


def _respuesta(status_code=200, cuerpo=None):
    respuesta = MagicMock()
    respuesta.status_code = status_code
    respuesta.json.return_value = cuerpo if cuerpo is not None else {"sent": True}
    return respuesta


class WhapiProviderTests(TestCase):
    """El provider debe generar exactamente el mismo request que el código
    legacy de enviar_mensaje.py (payload y headers byte-idénticos)."""

    @patch("apps.whatsapp.providers.whapi.requests.post")
    def test_payload_y_headers_identicos_a_legacy(self, mock_post):
        mock_post.return_value = _respuesta(200)
        provider = WhapiProvider(token="token-prueba")

        resultado = provider.send_text("12345@g.us", "hola *mundo*")

        mock_post.assert_called_once_with(
            URL_MENSAJE,
            json={"to": "12345@g.us", "body": "hola *mundo*", "no_link_preview": True},
            headers={
                "Authorization": "Bearer token-prueba",
                "Content-Type": "application/json",
            },
        )
        self.assertTrue(resultado.exito)
        self.assertEqual(resultado.proveedor, "whapi")
        self.assertEqual(resultado.status_code, 200)

    @patch("apps.whatsapp.providers.whapi.requests.post")
    def test_status_no_200_es_fallo(self, mock_post):
        mock_post.return_value = _respuesta(500, {"error": "boom"})
        resultado = WhapiProvider(token="t").send_text("g", "m")
        self.assertFalse(resultado.exito)
        self.assertEqual(resultado.status_code, 500)
        self.assertEqual(resultado.detalle, {"error": "boom"})

    @patch("apps.whatsapp.providers.whapi.requests.post")
    def test_error_de_conexion_es_fallo(self, mock_post):
        import requests as requests_lib

        mock_post.side_effect = requests_lib.ConnectionError("sin red")
        resultado = WhapiProvider(token="t").send_text("g", "m")
        self.assertFalse(resultado.exito)
        self.assertIsNone(resultado.status_code)

    def test_no_disponible_sin_token(self):
        self.assertFalse(WhapiProvider(token=None).disponible())
        self.assertTrue(WhapiProvider(token="x").disponible())


class ProviderChainTests(TestCase):
    @override_settings(WHATSAPP_PROVIDERS=["whapi"])
    @patch("apps.whatsapp.providers.whapi.WhapiProvider.disponible", return_value=True)
    def test_chain_solo_whapi(self, _):
        chain = get_provider_chain()
        self.assertEqual([p.nombre for p in chain], ["whapi"])

    @override_settings(WHATSAPP_PROVIDERS=["whapi", "openwa"], OPENWA_BASE_URL=None)
    @patch("apps.whatsapp.providers.whapi.WhapiProvider.disponible", return_value=True)
    def test_openwa_sin_config_se_omite(self, _):
        chain = get_provider_chain()
        self.assertEqual([p.nombre for p in chain], ["whapi"])

    @override_settings(WHATSAPP_PROVIDERS=["whapi", "openwa"])
    def test_fallback_al_segundo_proveedor(self):
        fallo = ResultadoEnvio(exito=False, proveedor="whapi", status_code=500)
        exito = ResultadoEnvio(exito=True, proveedor="openwa", status_code=200)
        with patch(
            "apps.whatsapp.providers.whapi.WhapiProvider.disponible", return_value=True
        ), patch(
            "apps.whatsapp.providers.whapi.WhapiProvider.send_text", return_value=fallo
        ), patch(
            "apps.whatsapp.providers.openwa.OpenWAProvider.disponible", return_value=True
        ), patch(
            "apps.whatsapp.providers.openwa.OpenWAProvider.send_text", return_value=exito
        ):
            resultado = enviar_texto("g", "m")
        self.assertTrue(resultado.exito)
        self.assertEqual(resultado.proveedor, "openwa")
