import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.whatsapp.api.enviar_mensaje import enviar_alertas_automatico
from apps.whatsapp.utils import ordenar_alertas_por_fecha


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


class OrdenarAlertasPorFechaTests(SimpleTestCase):
    def test_ordena_por_fecha_y_hora_cuando_estan_separadas(self):
        alertas = [
            {"id": "c", "fecha": "2024-01-03", "hora": "18:45"},
            {"id": "b", "fecha": "2024-01-03", "hora": "08:15"},
            {"id": "a", "fecha": "2024-01-02"},
        ]

        ordenadas = ordenar_alertas_por_fecha(alertas)

        self.assertEqual([alerta["id"] for alerta in ordenadas], ["a", "b", "c"])

    def test_ordena_usando_campo_time(self):
        alertas = [
            {"id": "primera", "fecha_publicacion": "2024-05-01", "time": "07:30"},
            {"id": "segunda", "fecha_publicacion": "2024-05-01", "time": "19:10"},
        ]

        ordenadas = ordenar_alertas_por_fecha(alertas)

        self.assertEqual([alerta["id"] for alerta in ordenadas], ["primera", "segunda"])

    def test_ordena_cuando_fecha_tiene_hora_en_formato_12h(self):
        alertas = [
            {"id": "tercera", "fecha_publicacion": "2025-09-14 7:42:07 PM"},
            {"id": "primera", "fecha_publicacion": "2025-09-14 2:28:06 PM"},
            {"id": "segunda", "fecha_publicacion": "2025-09-14 4:08:08 PM"},
            {"id": "cuarta", "fecha_publicacion": "2025-09-17 11:35:27 PM"},
        ]

        ordenadas = ordenar_alertas_por_fecha(alertas)

        self.assertEqual(
            [alerta["id"] for alerta in ordenadas],
            ["primera", "segunda", "tercera", "cuarta"],
        )

    def test_ordena_cuando_indicador_am_pm_tiene_puntos(self):
        alertas = [
            {"id": "tercera", "fecha_publicacion": "2025-09-14 7:42:07 p. m."},
            {"id": "primera", "fecha_publicacion": "2025-09-14 2:28:06 a. m."},
            {"id": "segunda", "fecha_publicacion": "2025-09-14 4:08:08 p. m."},
        ]

        ordenadas = ordenar_alertas_por_fecha(alertas)

        self.assertEqual(
            [alerta["id"] for alerta in ordenadas],
            ["primera", "segunda", "tercera"],
        )
