from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.whatsapp.api.enviar_mensaje import CapturaAlertasRedesAPIView


class CapturaAlertasRedesAPIViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    @patch("apps.whatsapp.api.enviar_mensaje.DetalleEnvio.objects.filter")
    @patch("apps.whatsapp.api.enviar_mensaje.TemplateConfig.objects.filter")
    @patch("apps.whatsapp.api.enviar_mensaje.get_object_or_404")
    def test_formatea_reach_y_engagement_con_prefijos(
        self,
        mock_get_object,
        mock_template_filter,
        mock_detalle_filter,
    ):
        mock_get_object.return_value = SimpleNamespace(codigo_acceso="12345")

        template_config = SimpleNamespace(
            config_campos={
                "titulo": {"orden": 1},
                "reach": {"orden": 2},
                "engagement": {"orden": 3},
            },
            nombre="redes justa",
        )
        mock_template_filter.return_value.first.return_value = template_config

        mock_detalle_filter.return_value.first.return_value = None

        payload = {
            "proyecto_id": "proyecto-1",
            "alertas": [
                {
                    "id": "alerta-1",
                    "titulo": "Titulo",
                    "contenido": "Contenido",
                    "fecha": "2024-01-01T00:00:00Z",
                    "autor": "Autor",
                    "reach": 1500,
                    "engagement": 75,
                }
            ],
        }

        request = self.factory.post("/whatsapp/redes/", payload, format="json")
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
        response = CapturaAlertasRedesAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        procesadas = response.data["procesadas"]
        self.assertEqual(len(procesadas), 1)
        mensaje_formateado = procesadas[0]["mensaje_formateado"]
        self.assertIn("seguidores: 1500", mensaje_formateado)
        self.assertIn("reach: 75", mensaje_formateado)

        mock_template_filter.assert_called_once()
        mock_detalle_filter.assert_called_once()
