from io import BytesIO

import openpyxl
from django.test import Client, TestCase
from django.utils import timezone

from apps.base.api.filtros import DetalleEnvioFilter
from apps.base.models import DetalleEnvio, Redes
from apps.proyectos.models import Proyecto


class DetalleEnvioFilterEstadoTests(TestCase):
    """El frontend envía estado_enviado=ENVIADO|FALLIDO; el filtro debe
    entenderlos (además de true/false) en lugar de ignorarlos."""

    def setUp(self):
        self.proyecto = Proyecto.objects.create(
            nombre="Proyecto Test",
            codigo_acceso="12345@g.us",
        )
        self.enviado = DetalleEnvio.objects.create(
            proyecto=self.proyecto, estado_enviado=True
        )
        self.fallido = DetalleEnvio.objects.create(
            proyecto=self.proyecto, estado_enviado=False
        )

    def _filtrar(self, valor):
        filtro = DetalleEnvioFilter(
            {"estado_enviado": valor}, queryset=DetalleEnvio.objects.all()
        )
        return list(filtro.qs)

    def test_enviado_filtra_solo_enviados(self):
        self.assertEqual(self._filtrar("ENVIADO"), [self.enviado])

    def test_fallido_filtra_solo_no_enviados(self):
        self.assertEqual(self._filtrar("FALLIDO"), [self.fallido])

    def test_valores_booleanos_siguen_funcionando(self):
        self.assertEqual(self._filtrar("true"), [self.enviado])
        self.assertEqual(self._filtrar("false"), [self.fallido])

    def test_valor_desconocido_no_filtra(self):
        self.assertEqual(len(self._filtrar("cualquiercosa")), 2)


class ExportarHistorialExcelTests(TestCase):
    """La descarga de Excel debe respetar los mismos filtros que el listado."""

    def setUp(self):
        self.client = Client()
        self.proyecto_a = Proyecto.objects.create(
            nombre="Alertas Marketing", codigo_acceso="111@g.us"
        )
        self.proyecto_b = Proyecto.objects.create(
            nombre="Otro Proyecto", codigo_acceso="222@g.us"
        )
        red_a = Redes.objects.create(
            contenido="contenido a",
            fecha_publicacion=timezone.now(),
            url="https://twitter.com/x/status/1",
            proyecto=self.proyecto_a,
        )
        red_b = Redes.objects.create(
            contenido="contenido b",
            fecha_publicacion=timezone.now(),
            url="https://twitter.com/x/status/2",
            proyecto=self.proyecto_b,
        )
        DetalleEnvio.objects.create(
            proyecto=self.proyecto_a, red_social=red_a, estado_enviado=True
        )
        DetalleEnvio.objects.create(
            proyecto=self.proyecto_b, red_social=red_b, estado_enviado=False
        )

    def _descargar(self, params=""):
        response = self.client.get(f"/api/exportar-historial/{params}")
        self.assertEqual(response.status_code, 200)
        wb = openpyxl.load_workbook(BytesIO(response.content))
        ws = wb.active
        # Filas de datos (sin encabezado)
        return [row for row in ws.iter_rows(min_row=2, values_only=True)]

    def test_sin_filtros_descarga_todo(self):
        self.assertEqual(len(self._descargar()), 2)

    def test_filtra_por_proyecto_nombre(self):
        filas = self._descargar("?proyecto_nombre=Marketing")
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0][0], "Alertas Marketing")

    def test_filtra_por_estado_enviado(self):
        filas = self._descargar("?estado_enviado=ENVIADO")
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0][0], "Alertas Marketing")

    def test_filtros_combinados(self):
        filas = self._descargar("?proyecto_nombre=Marketing&estado_enviado=FALLIDO")
        self.assertEqual(len(filas), 0)
