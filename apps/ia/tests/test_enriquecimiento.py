from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.base.models import Articulo, DetalleEnvio, Redes, RedesSociales
from apps.ia.models import EnriquecimientoLog
from apps.ia.services.enriquecimiento import orchestrator
from apps.proyectos.models import Proyecto


class OrquestadorEnriquecimientoTests(TestCase):
    def setUp(self):
        self.proyecto = Proyecto.objects.create(
            nombre="LOREAL", codigo_acceso="g@g.us", tipo_alerta="redes"
        )

    def _red(self, red="Facebook", **kwargs):
        defaults = {
            "contenido": "post",
            "fecha_publicacion": timezone.now(),
            "url": "https://facebook.com/p/1",
            "autor": None,
            "reach": None,
            "engagement": 30,
        }
        defaults.update(kwargs)
        red_obj = Redes.objects.create(
            red_social=RedesSociales.objects.create(nombre=red),
            proyecto=self.proyecto,
            **defaults,
        )
        detalle = DetalleEnvio.objects.create(
            proyecto=self.proyecto,
            red_social=red_obj,
            estado_pipeline=DetalleEnvio.PIPELINE_ENRIQUECIENDO,
        )
        return red_obj, detalle

    @patch("apps.ia.services.enriquecimiento.orchestrator.brightdata.completar_red")
    def test_solo_llena_vacios_y_no_toca_engagement(self, mock_bd):
        # C4: aunque la fuente traiga engagement distinto, el existente no se pisa
        mock_bd.return_value = {"autor": "@real", "reach": 12000, "engagement": 999}
        red, detalle = self._red(engagement=30)

        completados = orchestrator.completar(detalle, ["autor", "reach"])

        red.refresh_from_db()
        self.assertEqual(red.autor, "@real")
        self.assertEqual(red.reach, 12000)
        self.assertEqual(red.engagement, 30)  # intacto
        campos = {c["campo"] for c in completados}
        self.assertEqual(campos, {"autor", "reach"})
        self.assertEqual(
            EnriquecimientoLog.objects.filter(detalle_envio=detalle, exito=True).count(), 2
        )

    @patch("apps.ia.services.enriquecimiento.orchestrator.brightdata.completar_red")
    def test_reach_cero_se_trata_como_faltante(self, mock_bd):
        mock_bd.return_value = {"reach": 5000}
        red, detalle = self._red(reach=0, autor="@x")
        orchestrator.completar(detalle, ["reach"])
        red.refresh_from_db()
        self.assertEqual(red.reach, 5000)

    @patch("apps.ia.services.enriquecimiento.orchestrator.scrapegraph.completar_red")
    @patch("apps.ia.services.enriquecimiento.orchestrator.brightdata.completar_red")
    def test_precedencia_facebook_brightdata_primero(self, mock_bd, mock_sg):
        mock_bd.return_value = {"autor": "@bd"}
        red, detalle = self._red(red="Facebook")
        orchestrator.completar(detalle, ["autor"])
        red.refresh_from_db()
        self.assertEqual(red.autor, "@bd")
        mock_sg.assert_not_called()

    @patch("apps.ia.services.enriquecimiento.orchestrator.brightdata.completar_red")
    @patch("apps.ia.services.enriquecimiento.orchestrator.scrapegraph.completar_red")
    def test_precedencia_twitter_scrapegraph_primero_con_fallback(self, mock_sg, mock_bd):
        mock_sg.return_value = {}
        mock_bd.return_value = {"autor": "@bd"}
        red, detalle = self._red(red="Twitter", url="https://twitter.com/u/status/1")
        orchestrator.completar(detalle, ["autor"])
        red.refresh_from_db()
        self.assertEqual(red.autor, "@bd")
        mock_sg.assert_called_once()

    def test_fallo_total_queda_auditado(self):
        with patch(
            "apps.ia.services.enriquecimiento.orchestrator.brightdata.completar_red",
            return_value={},
        ), patch(
            "apps.ia.services.enriquecimiento.orchestrator.scrapegraph.completar_red",
            return_value={},
        ):
            red, detalle = self._red()
            completados = orchestrator.completar(detalle, ["autor"])
        self.assertEqual(completados, [])
        log = EnriquecimientoLog.objects.get(detalle_envio=detalle)
        self.assertFalse(log.exito)

    @patch("apps.ia.services.enriquecimiento.orchestrator.similarweb.obtener_reach_dominio")
    def test_medios_reach_por_similarweb(self, mock_sw):
        mock_sw.return_value = 250000
        articulo = Articulo.objects.create(
            titulo="Nota",
            contenido="c",
            url="https://elcomercio.pe/nota",
            fecha_publicacion=timezone.now(),
            proyecto=self.proyecto,
        )
        detalle = DetalleEnvio.objects.create(
            proyecto=self.proyecto,
            medio=articulo,
            estado_pipeline=DetalleEnvio.PIPELINE_ENRIQUECIENDO,
        )
        completados = orchestrator.completar(detalle, ["reach"])
        articulo.refresh_from_db()
        self.assertEqual(articulo.reach, 250000)
        self.assertEqual(completados[0]["fuente"], "similarweb")

    def test_medios_ubicacion_por_tld(self):
        articulo = Articulo.objects.create(
            titulo="Nota",
            contenido="c",
            url="https://elcomercio.pe/nota",
            fecha_publicacion=timezone.now(),
            proyecto=self.proyecto,
        )
        detalle = DetalleEnvio.objects.create(
            proyecto=self.proyecto,
            medio=articulo,
            estado_pipeline=DetalleEnvio.PIPELINE_ENRIQUECIENDO,
        )
        completados = orchestrator.completar(detalle, ["ubicacion"])
        articulo.refresh_from_db()
        self.assertEqual(articulo.ubicacion, "Perú")
        self.assertEqual(completados[0]["fuente"], "heuristica")
