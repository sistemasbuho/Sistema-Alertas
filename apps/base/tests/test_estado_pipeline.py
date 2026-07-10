from django.test import TestCase
from django.utils import timezone

from apps.base.models import DetalleEnvio, Redes
from apps.proyectos.models import Proyecto


class EstadoPipelineTests(TestCase):
    """La transición de estado_pipeline debe mantener sincronizados los
    booleanos legacy (estado_enviado / estado_revisado) que consume el
    frontend actual."""

    def setUp(self):
        self.proyecto = Proyecto.objects.create(
            nombre="Proyecto Test",
            codigo_acceso="12345@g.us",
        )
        self.red = Redes.objects.create(
            contenido="contenido de prueba",
            fecha_publicacion=timezone.now(),
            url="https://twitter.com/x/status/1",
            proyecto=self.proyecto,
        )
        self.detalle = DetalleEnvio.objects.create(
            proyecto=self.proyecto,
            red_social=self.red,
        )

    def test_default_es_manual(self):
        self.assertEqual(self.detalle.estado_pipeline, DetalleEnvio.PIPELINE_MANUAL)
        self.assertFalse(self.detalle.estado_enviado)
        self.assertEqual(self.detalle.intentos_ia, 0)
        self.assertIsNone(self.detalle.proveedor_envio)

    def test_enviada_marca_enviado_y_fin_envio(self):
        self.detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_ENVIADA)
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.estado_pipeline, DetalleEnvio.PIPELINE_ENVIADA)
        self.assertTrue(self.detalle.estado_enviado)
        self.assertIsNotNone(self.detalle.fin_envio)

    def test_error_envio_deja_no_enviado(self):
        self.detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_ERROR_ENVIO)
        self.detalle.refresh_from_db()
        self.assertFalse(self.detalle.estado_enviado)

    def test_cola_excepciones_marca_no_revisado(self):
        self.detalle.estado_revisado = True
        self.detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_COLA_EXCEPCIONES)
        self.detalle.refresh_from_db()
        self.assertFalse(self.detalle.estado_revisado)

    def test_resoluciones_humanas_marcan_revisado(self):
        for estado in (
            DetalleEnvio.PIPELINE_APROBADA_HUMANA,
            DetalleEnvio.PIPELINE_DESCARTADA_HUMANA,
            DetalleEnvio.PIPELINE_DESCARTADA_IA,
        ):
            self.detalle.estado_revisado = False
            self.detalle.aplicar_estado_pipeline(estado)
            self.detalle.refresh_from_db()
            self.assertTrue(self.detalle.estado_revisado, estado)

    def test_estados_intermedios_no_tocan_booleanos(self):
        self.detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_PENDIENTE_IA)
        self.detalle.refresh_from_db()
        self.assertFalse(self.detalle.estado_enviado)
        self.assertFalse(self.detalle.estado_revisado)
