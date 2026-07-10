from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.base.models import DetalleEnvio, Redes, RedesSociales, TemplateConfig
from apps.ia.models import EvaluacionIA
from apps.ia.services.vertex import MetadatosLLM
from apps.ia.tasks import clasificar_alerta
from apps.proyectos.models import Proyecto
from apps.whatsapp.providers.base import ResultadoEnvio

SALIDA_LLM = {
    "relevante": True,
    "relevancia_score": 0.97,
    "tonalidad": "negativo",
    "tonalidad_score": 0.93,
    "categoria_sector": "belleza",
    "pais": "PE",
    "pais_score": 0.91,
    "regla_no_alertar": None,
    "marca_detectada": "Elvive",
    "razones": ["denuncia de daño capilar por Elvive"],
}
META = MetadatosLLM(modelo="gemini-test", latencia_ms=90)


class PipelineEndToEndTests(TestCase):
    """CSV→clasificación(mock)→gate→envío(mock provider)→enviada, con
    bandera/semáforo/sector en la primera línea del mensaje."""

    def setUp(self):
        self.proyecto = Proyecto.objects.create(
            nombre="LOREAL",
            codigo_acceso="grupo-loreal@g.us",
            tipo_alerta="redes",
            tipo_envio="automatico",
        )
        call_command("cargar_matriz_loreal", str(self.proyecto.id), "--activar", "--modo", "activo")
        TemplateConfig.objects.create(
            nombre="plantilla redes",
            app_label="base",
            model_name="Redes",
            proyecto=self.proyecto,
            config_campos={
                "contenido": {"orden": 1, "activo": True, "estilo": {}},
                "autor": {"orden": 2, "activo": True, "estilo": {"negrita": True}},
                "url": {"orden": 3, "activo": True, "estilo": {}},
            },
        )
        self.red = Redes.objects.create(
            contenido="El shampoo Elvive me quemó el cuero cabelludo, demandaré",
            fecha_publicacion=timezone.now(),
            url="https://twitter.com/u/status/7",
            autor="@denunciante",
            reach=9000,   # alto (>8000)
            engagement=200,  # alto en twitter (>100)
            red_social=RedesSociales.objects.create(nombre="Twitter"),
            proyecto=self.proyecto,
        )
        self.detalle = DetalleEnvio.objects.create(
            proyecto=self.proyecto,
            red_social=self.red,
            estado_pipeline=DetalleEnvio.PIPELINE_PENDIENTE_IA,
        )

    @patch("apps.whatsapp.services.envio.enviar_texto")
    @patch("apps.whatsapp.api.enviar_mensaje.enviar_alertas_a_monitoreo", return_value={})
    @patch("apps.ia.services.vertex.clasificar", return_value=(SALIDA_LLM, META))
    def test_flujo_completo_hasta_enviada(self, mock_llm, mock_monitoreo, mock_envio):
        mock_envio.return_value = ResultadoEnvio(exito=True, proveedor="whapi", status_code=200)

        clasificar_alerta.apply(args=[str(self.detalle.id)])

        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.estado_pipeline, DetalleEnvio.PIPELINE_ENVIADA)
        self.assertTrue(self.detalle.estado_enviado)
        self.assertEqual(self.detalle.proveedor_envio, "whapi")
        self.assertIsNotNone(self.detalle.fin_envio)

        # El mensaje enviado lleva bandera 🇵🇪, semáforo 🔴 (ambas variables
        # altas) y emoji de sector 💄 en la primera línea
        grupo, mensaje = mock_envio.call_args[0]
        self.assertEqual(grupo, "grupo-loreal@g.us")
        primera_linea = mensaje.split("\n")[0]
        for emoji in ("🇵🇪", "🔴", "💄"):
            self.assertIn(emoji, primera_linea)
        self.assertIn("Elvive", mensaje)
        self.assertIn("*@denunciante*", mensaje)

        # Auditoría D5 completa
        evaluacion = EvaluacionIA.objects.get(detalle_envio=self.detalle)
        self.assertEqual(evaluacion.decision, EvaluacionIA.DECISION_AUTO_ENVIAR)
        self.assertEqual(evaluacion.riesgo, "alto")
        self.assertEqual(evaluacion.pais_detectado, "PE")
        self.assertTrue(evaluacion.razones)
        self.assertIsNotNone(evaluacion.snapshot_matriz)

        mock_monitoreo.assert_called_once()

    @patch("apps.whatsapp.services.envio.enviar_texto")
    @patch("apps.whatsapp.api.enviar_mensaje.enviar_alertas_a_monitoreo", return_value={})
    @patch("apps.ia.services.vertex.clasificar", return_value=(SALIDA_LLM, META))
    def test_fallo_de_envio_marca_error(self, mock_llm, mock_monitoreo, mock_envio):
        mock_envio.return_value = ResultadoEnvio(
            exito=False, proveedor="whapi", status_code=500, detalle="boom"
        )
        clasificar_alerta.apply(args=[str(self.detalle.id)])
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.estado_pipeline, DetalleEnvio.PIPELINE_ERROR_ENVIO)
        self.assertFalse(self.detalle.estado_enviado)
        mock_monitoreo.assert_not_called()

    @patch("apps.whatsapp.services.envio.enviar_texto")
    @patch("apps.whatsapp.api.enviar_mensaje.enviar_alertas_a_monitoreo", return_value={})
    @patch("apps.ia.services.vertex.clasificar", return_value=(SALIDA_LLM, META))
    def test_reenvio_es_idempotente(self, mock_llm, mock_monitoreo, mock_envio):
        mock_envio.return_value = ResultadoEnvio(exito=True, proveedor="whapi", status_code=200)
        clasificar_alerta.apply(args=[str(self.detalle.id)])

        from apps.whatsapp.services.envio import enviar_detalle

        self.assertEqual(enviar_detalle(str(self.detalle.id)), "omitida")
        self.assertEqual(mock_envio.call_count, 1)
