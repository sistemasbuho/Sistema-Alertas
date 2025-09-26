import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.whatsapp.api.enviar_mensaje import enviar_alertas_automatico


class EnviarAlertasAutomaticoFechaTests(SimpleTestCase):
    def test_enviar_alertas_automatico_formatea_fecha_legible(self):
        proyecto_id = uuid.uuid4()
        usuario_id = uuid.uuid4()
        alertas = [
            {
                "id": "alerta-1",
                "contenido": "Contenido",
                "titulo": "Titulo",
                "autor": "Autor",
                "fecha": "2025-09-23T16:01:38.000Z",
                "url": "http://example.com",
                "reach": "",
                "engagement": "",
            }
        ]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        plantilla = SimpleNamespace(
            config_campos={"fecha_publicacion": {"orden": 1, "label": "Fecha"}},
            nombre="Plantilla",
        )
        proyecto = SimpleNamespace(codigo_acceso="12345")
        usuario = SimpleNamespace(id=usuario_id)

        dummy_detalle = SimpleNamespace(estado_enviado=False)
        dummy_detalle.save = lambda: None

        class DummyQueryset(list):
            def first(self):
                return self[0] if self else None

        plantilla_queryset = DummyQueryset([plantilla])

        with patch("apps.whatsapp.api.enviar_mensaje.requests.post", return_value=mock_response), patch(
            "apps.whatsapp.api.enviar_mensaje.formatear_mensaje"
        ) as mock_formatear_mensaje, patch(
            "apps.whatsapp.api.enviar_mensaje.enviar_alertas_a_monitoreo", return_value={}
        ), patch(
            "apps.whatsapp.api.enviar_mensaje.Proyecto.objects.get", return_value=proyecto
        ), patch(
            "apps.whatsapp.api.enviar_mensaje.TemplateConfig.objects.filter", return_value=plantilla_queryset
        ), patch(
            "apps.whatsapp.api.enviar_mensaje.get_user_model", return_value=SimpleNamespace(objects=SimpleNamespace(get=lambda id: usuario))
        ), patch(
            "apps.whatsapp.api.enviar_mensaje.DetalleEnvio.objects.update_or_create", return_value=(dummy_detalle, True)
        ):
            mock_formatear_mensaje.side_effect = (
                lambda alerta_data, *args, **kwargs: alerta_data.get("fecha_publicacion")
            )

            enviar_alertas_automatico(
                proyecto_id,
                "medios",
                alertas,
                usuario_id=usuario_id,
            )

        alerta_pasada = mock_formatear_mensaje.call_args[0][0]
        self.assertEqual(alerta_pasada["fecha_publicacion"], "2025-09-23 4:01:38 PM")
