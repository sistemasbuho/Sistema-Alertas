from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.utils.datastructures import MultiValueDict
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from apps.base.api.ingestion import IngestionAPIView
from apps.base.api.utils import formatear_fecha_respuesta
from apps.base.models import Articulo


class IngestionAPITests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.proyecto_id = "123e4567-e89b-12d3-a456-426614174000"
        self.ultimo_registro_articulo = None
        self.ultimo_registro_red = None

    def _mock_proyecto(
        self, mock_proyecto, criterios=None, tipo_alerta="medios", nombre="Proyecto Test"
    ):
        criterios = criterios or []
        proyecto = SimpleNamespace(
            id=self.proyecto_id,
            get_criterios_aceptacion_list=lambda: criterios,
            tipo_alerta=tipo_alerta,
            nombre=nombre,
        )
        mock_proyecto.objects.filter.return_value.first.return_value = proyecto

    @patch("apps.base.api.ingestion.Proyecto")
    def test_detects_medios_twk_from_csv_and_forwards_payload(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
        content = (
            "title,content,published,extra_author_attributes.name,reach,url\n"
            "Titulo,Contenido,2024-01-01,Autor,1000,http://example.com/articulo\n"
        )
        uploaded = SimpleUploadedFile(
            "medios.csv",
            content.encode("utf-8"),
            content_type="text/csv",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": uploaded},
            format="multipart",
        )

        with patch.object(
            IngestionAPIView,
            "_obtener_usuario_sistema",
            return_value=SimpleNamespace(id=2),
        ), patch.object(
            IngestionAPIView,
            "_crear_articulo",
            side_effect=self._fake_crear_articulo,
        ), patch.object(
            IngestionAPIView,
            "_crear_red_social",
            side_effect=self._fake_crear_red_social,
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        listado = response.data["listado"]
        self.assertEqual(len(listado), 1)
        self.assertEqual(listado[0]["autor"], "Autor")
        self.assertEqual(listado[0]["tipo"], "medios")
        self.assertEqual(response.data["duplicados"], 0)
        self.assertEqual(response.data["descartados"], 0)
        self.assertEqual(response.data["mensaje"], "1 registros creados")
        self.assertEqual(response.data["proyecto_nombre"], "Proyecto Test")

    @patch("apps.base.api.ingestion.Proyecto")
    def test_detects_global_news_provider(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
        content = (
            "Título,Resumen - Aclaracion,Fecha,Autor - Conductor,Medio,URL\n"
            "Noticia,Contenido GN,2024-03-01,Autor GN,Canal GN,http://example.com/global-news\n"
        )
        uploaded = SimpleUploadedFile(
            "global_news.csv",
            content.encode("utf-8"),
            content_type="text/csv",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": uploaded},
            format="multipart",
        )

        with patch.object(
            IngestionAPIView,
            "_obtener_usuario_sistema",
            return_value=SimpleNamespace(id=2),
        ), patch.object(
            IngestionAPIView,
            "_crear_articulo",
            side_effect=self._fake_crear_articulo,
        ), patch.object(
            IngestionAPIView,
            "_crear_red_social",
            side_effect=self._fake_crear_red_social,
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["proveedor"], "global_news")
        listado = response.data["listado"]
        self.assertEqual(len(listado), 1)
        alerta = listado[0]
        self.assertEqual(alerta["autor"], "Autor GN")
        self.assertEqual(alerta["titulo"], "Noticia")
        self.assertEqual(alerta["contenido"], "Contenido GN")

    @patch.object(Articulo.objects, "filter")
    def test_es_url_duplicada_por_proyecto_normaliza_variantes(self, mock_filter):
        view = IngestionAPIView()
        proyecto = SimpleNamespace(id=self.proyecto_id)

        mock_queryset = mock_filter.return_value
        mock_queryset.values_list.return_value = ["https://example.com/noticia"]

        es_duplicado = view._es_url_duplicada_por_proyecto(
            Articulo,
            proyecto,
            "http://www.example.com/noticia/",
        )

        self.assertTrue(es_duplicado)
        mock_filter.assert_called_once_with(proyecto=proyecto)

    @patch("apps.base.api.ingestion.Proyecto")
    def test_detects_stakeholders_provider(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
        content = (
            "Titular,Resumen,Fecha,Autor,Fuente,URL\n"
            "Stakeholder News,Resumen SH,2024-04-15,Autor SH,FUENTE,http://example.com/stakeholders\n"
        )
        uploaded = SimpleUploadedFile(
            "stakeholders.csv",
            content.encode("utf-8"),
            content_type="text/csv",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": uploaded},
            format="multipart",
        )

        with patch.object(
            IngestionAPIView,
            "_obtener_usuario_sistema",
            return_value=SimpleNamespace(id=2),
        ), patch.object(
            IngestionAPIView,
            "_crear_articulo",
            side_effect=self._fake_crear_articulo,
        ), patch.object(
            IngestionAPIView,
            "_crear_red_social",
            side_effect=self._fake_crear_red_social,
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["proveedor"], "stakeholders")
        listado = response.data["listado"]
        self.assertEqual(len(listado), 1)
        alerta = listado[0]
        self.assertEqual(alerta["autor"], "Autor SH")
        self.assertEqual(alerta["titulo"], "Stakeholder News")
        self.assertEqual(alerta["contenido"], "Resumen SH")

    @patch("apps.base.api.ingestion.Proyecto")
    def test_detects_determ_medios_provider(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
        content = (
            "TITLE,MENTION_SNIPPET,DATE,AUTHOR,FROM,URL\n"
            "Determinacion,Resumen DM,2024-05-20,Autor DM,Fuente DM,http://example.com/determ-medios\n"
        )
        uploaded = SimpleUploadedFile(
            "determ_medios.csv",
            content.encode("utf-8"),
            content_type="text/csv",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": uploaded},
            format="multipart",
        )

        with patch.object(
            IngestionAPIView,
            "_obtener_usuario_sistema",
            return_value=SimpleNamespace(id=2),
        ), patch.object(
            IngestionAPIView,
            "_crear_articulo",
            side_effect=self._fake_crear_articulo,
        ), patch.object(
            IngestionAPIView,
            "_crear_red_social",
            side_effect=self._fake_crear_red_social,
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["proveedor"], "determ_medios")
        listado = response.data["listado"]
        self.assertEqual(len(listado), 1)
        alerta = listado[0]
        self.assertEqual(alerta["autor"], "Autor DM")
        self.assertEqual(alerta["titulo"], "Determinacion")
        self.assertEqual(alerta["contenido"], "Resumen DM")

    @patch("apps.base.api.ingestion.Proyecto")
    def test_rechaza_archivo_sin_columna_url(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
        content = (
            "title,content,published,extra_author_attributes.name,reach\n"
            "Titulo,Contenido,2024-01-01,Autor,1000\n"
        )
        uploaded = SimpleUploadedFile(
            "medios.csv",
            content.encode("utf-8"),
            content_type="text/csv",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": uploaded},
            format="multipart",
        )

        response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("columna 'url'", response.data["detail"].lower())

    @patch("apps.base.api.ingestion.Proyecto")
    def test_rechaza_archivo_con_columna_url_sin_datos(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
        content = (
            "title,content,published,extra_author_attributes.name,reach,url\n"
            "Titulo,Contenido,2024-01-01,Autor,1000,\n"
        )
        uploaded = SimpleUploadedFile(
            "medios.csv",
            content.encode("utf-8"),
            content_type="text/csv",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": uploaded},
            format="multipart",
        )

        response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("valor válido", response.data["detail"].lower())

    def test_parse_xlsx_ignora_columnas_vacias(self):
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(
            [
                "title",
                "content",
                "published",
                "extra_author_attributes.name",
                "reach",
                "url",
                "columna_vacia",
            ]
        )
        sheet.append(
            [
                "Titulo",
                "Contenido",
                "2024-01-01",
                "Autor",
                "1000",
                "http://example.com/desde-xlsx",
                None,
            ]
        )
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)

        view = IngestionAPIView()
        headers, rows = view._parse_xlsx(buffer)

        self.assertIn("url", headers)
        self.assertTrue(rows)
        self.assertNotIn("columna_vacia", rows[0])

    @patch("apps.base.api.ingestion.Proyecto")
    def test_respuesta_incluye_conteo_de_duplicados(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
        content = (
            "title,content,published,extra_author_attributes.name,reach,url\n"
            "Titulo,Contenido,2024-01-01,Autor,1000,http://example.com/articulo\n"
        )
        uploaded = SimpleUploadedFile(
            "medios.csv",
            content.encode("utf-8"),
            content_type="text/csv",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": uploaded},
            format="multipart",
        )

        with patch.object(
            IngestionAPIView,
            "_obtener_usuario_sistema",
            return_value=SimpleNamespace(id=2),
        ), patch.object(
            IngestionAPIView,
            "_crear_articulo",
            side_effect=ValueError("La URL ya existe para este proyecto"),
        ), patch.object(
            IngestionAPIView,
            "_crear_red_social",
            side_effect=self._fake_crear_red_social,
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["duplicados"], 1)
        self.assertEqual(response.data["descartados"], 0)
        self.assertIn("1 duplicados", response.data["mensaje"])
        self.assertEqual(len(response.data["errores"]), 1)

    @patch("apps.base.api.ingestion.Proyecto")
    def test_respuesta_sin_registros_incluye_nombre(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}", {}, format="multipart"
        )

        with patch.object(
            IngestionAPIView,
            "_extraer_registros_estandar",
            return_value=([{"proveedor": "medios"}], "medios", None),
        ), patch.object(
            IngestionAPIView, "_filtrar_por_criterios", return_value=[]
        ), patch.object(
            IngestionAPIView, "_notificar_ruta_externa"
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["proyecto_nombre"], "Proyecto Test")

    @patch("apps.base.api.ingestion.Proyecto")
    def test_detects_redes_twk_from_xlsx_and_forwards_payload(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto, tipo_alerta="redes")
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(
            [
                "content",
                "published",
                "extra_author_attributes.name",
                "reach",
                "engagement",
                "url",
                "red_social",
            ]
        )
        sheet.append(
            [
                "Hola",
                "2024-02-02",
                "User",
                "500",
                "42",
                "http://example.com/red-uno",
                "Twitter",
            ]
        )
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        uploaded = SimpleUploadedFile(
            "redes.xlsx",
            buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": uploaded},
            format="multipart",
        )

        with patch.object(
            IngestionAPIView,
            "_obtener_usuario_sistema",
            return_value=SimpleNamespace(id=2),
        ), patch.object(
            IngestionAPIView,
            "_crear_articulo",
            side_effect=self._fake_crear_articulo,
        ), patch.object(
            IngestionAPIView,
            "_crear_red_social",
            side_effect=self._fake_crear_red_social,
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        listado = response.data["listado"]
        self.assertEqual(len(listado), 1)
        alerta = listado[0]
        self.assertIsNone(self.ultimo_registro_articulo)
        self.assertIsNotNone(self.ultimo_registro_red)
        self.assertEqual(alerta["contenido"], self.ultimo_registro_red.get("contenido"))
        self.assertEqual(alerta["engagement"], self.ultimo_registro_red.get("engagement"))
        self.assertEqual(alerta["tipo"], "redes")
        self.assertEqual(response.data["duplicados"], 0)
        self.assertEqual(response.data["descartados"], 0)
        self.assertEqual(response.data["mensaje"], "1 registros creados")

    @patch("apps.base.api.ingestion.Proyecto")
    def test_respuesta_incluye_conteo_de_descartados(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
        content = (
            "title,content,published,extra_author_attributes.name,reach,url\n"
            "Titulo,Contenido,2024-01-01,Autor,1000,http://example.com/articulo\n"
        )
        uploaded = SimpleUploadedFile(
            "medios.csv",
            content.encode("utf-8"),
            content_type="text/csv",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": uploaded},
            format="multipart",
        )

        with patch.object(
            IngestionAPIView,
            "_obtener_usuario_sistema",
            return_value=SimpleNamespace(id=2),
        ), patch.object(
            IngestionAPIView,
            "_crear_articulo",
            side_effect=RuntimeError("Error inesperado"),
        ), patch.object(
            IngestionAPIView,
            "_crear_red_social",
            side_effect=self._fake_crear_red_social,
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["duplicados"], 0)
        self.assertEqual(response.data["descartados"], 1)
        self.assertIn("1 descartados", response.data["mensaje"])
        self.assertEqual(len(response.data["errores"]), 1)

    @patch("apps.base.api.ingestion.Proyecto")
    def test_redes_twk_trim_contenido_for_twitter_qt(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto, tipo_alerta="redes")
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(
            [
                "content",
                "published",
                "extra_author_attributes.name",
                "reach",
                "engagement",
                "url",
                "red_social",
            ]
        )
        sheet.append(
            [
                "Mensaje inicial QT @usuario comentario",
                "2024-03-03",
                "User",
                "500",
                "42",
                "http://example.com/red-dos",
                "Twitter",
            ]
        )
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        uploaded = SimpleUploadedFile(
            "redes.xlsx",
            buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": uploaded},
            format="multipart",
        )

        with patch.object(
            IngestionAPIView,
            "_obtener_usuario_sistema",
            return_value=SimpleNamespace(id=2),
        ), patch.object(
            IngestionAPIView,
            "_crear_articulo",
            side_effect=self._fake_crear_articulo,
        ), patch.object(
            IngestionAPIView,
            "_crear_red_social",
            side_effect=self._fake_crear_red_social,
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        alerta = response.data["listado"][0]
        self.assertIsNotNone(self.ultimo_registro_red)
        self.assertEqual(alerta["contenido"], self.ultimo_registro_red.get("contenido"))
        self.assertEqual(alerta["red_social"], None)
        self.assertEqual(alerta["tipo"], "redes")
        self.assertEqual(response.data["duplicados"], 0)
        self.assertEqual(response.data["descartados"], 0)

    @patch("apps.base.api.ingestion.Proyecto")
    def test_permite_multiples_archivos_en_una_misma_peticion(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
        content_uno = (
            "title,content,published,extra_author_attributes.name,reach,url\n"
            "Titulo 1,Contenido 1,2024-01-01,Autor 1,1000,http://example.com/articulo-1\n"
        )
        content_dos = (
            "title,content,published,extra_author_attributes.name,reach,url\n"
            "Titulo 2,Contenido 2,2024-02-02,Autor 2,500,http://example.com/articulo-2\n"
        )
        uploaded_uno = SimpleUploadedFile(
            "medios-uno.csv",
            content_uno.encode("utf-8"),
            content_type="text/csv",
        )
        uploaded_dos = SimpleUploadedFile(
            "medios-dos.csv",
            content_dos.encode("utf-8"),
            content_type="text/csv",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": [uploaded_uno, uploaded_dos]},
            format="multipart",
        )

        with patch.object(
            IngestionAPIView,
            "_obtener_usuario_sistema",
            return_value=SimpleNamespace(id=2),
        ), patch.object(
            IngestionAPIView,
            "_crear_articulo",
            side_effect=self._fake_crear_articulo,
        ), patch.object(
            IngestionAPIView,
            "_crear_red_social",
            side_effect=self._fake_crear_red_social,
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        listado = response.data["listado"]
        self.assertEqual(len(listado), 2)
        autores = {alerta["autor"] for alerta in listado}
        self.assertSetEqual(autores, {"Autor 1", "Autor 2"})
        self.assertEqual(response.data["duplicados"], 0)
        self.assertEqual(response.data["descartados"], 0)
        self.assertEqual(response.data["mensaje"], "2 registros creados")

    @patch("apps.base.api.ingestion.Proyecto")
    def test_permite_archivos_en_claves_distintas(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
        contenido_a = (
            "title,content,published,extra_author_attributes.name,reach,url\n"
            "Titulo A,Contenido A,2024-03-03,Autor A,1500,http://example.com/articulo-a\n"
        )
        contenido_b = (
            "title,content,published,extra_author_attributes.name,reach,url\n"
            "Titulo B,Contenido B,2024-04-04,Autor B,800,http://example.com/articulo-b\n"
        )
        archivo_a = SimpleUploadedFile(
            "medios-a.csv",
            contenido_a.encode("utf-8"),
            content_type="text/csv",
        )
        archivo_b = SimpleUploadedFile(
            "medios-b.csv",
            contenido_b.encode("utf-8"),
            content_type="text/csv",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": archivo_a, "archivo_secundario": archivo_b},
            format="multipart",
        )

        with patch.object(
            IngestionAPIView,
            "_obtener_usuario_sistema",
            return_value=SimpleNamespace(id=2),
        ), patch.object(
            IngestionAPIView,
            "_crear_articulo",
            side_effect=self._fake_crear_articulo,
        ), patch.object(
            IngestionAPIView,
            "_crear_red_social",
            side_effect=self._fake_crear_red_social,
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        listado = response.data["listado"]
        self.assertEqual(len(listado), 2)
        autores = {alerta["autor"] for alerta in listado}
        self.assertSetEqual(autores, {"Autor A", "Autor B"})
        self.assertEqual(response.data["duplicados"], 0)
        self.assertEqual(response.data["descartados"], 0)
        self.assertEqual(response.data["mensaje"], "2 registros creados")

    @patch("apps.base.api.ingestion.Proyecto")
    def test_aplica_filtro_de_criterios_de_aceptacion(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto, criterios=["alerta"])
        content = (
            "title,content,published,extra_author_attributes.name,reach,url\n"
            "Mensaje sin match,Contenido,2024-01-01,Autor,1000,http://example.com/articulo-sin-match\n"
            "Alerta importante,Contenido,2024-01-01,Autor,1000,http://example.com/articulo-alerta\n"
        )
        uploaded = SimpleUploadedFile(
            "medios.csv",
            content.encode("utf-8"),
            content_type="text/csv",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": uploaded},
            format="multipart",
        )

        with patch.object(
            IngestionAPIView,
            "_obtener_usuario_sistema",
            return_value=SimpleNamespace(id=2),
        ), patch.object(
            IngestionAPIView,
            "_crear_articulo",
            side_effect=self._fake_crear_articulo,
        ), patch.object(
            IngestionAPIView,
            "_crear_red_social",
            side_effect=self._fake_crear_red_social,
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        payload = response.data
        self.assertEqual(len(payload["listado"]), 1)
        self.assertEqual(payload["listado"][0]["titulo"], "Alerta importante")
        self.assertEqual(payload["duplicados"], 0)
        self.assertEqual(payload["descartados"], 0)
        self.assertEqual(payload["mensaje"], "1 registros creados")

    @patch("apps.base.api.ingestion.Proyecto")
    def test_filtro_de_criterios_sin_coincidencias_no_reenvia(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto, criterios=["alerta"])
        content = (
            "title,content,published,extra_author_attributes.name,reach,url\n"
            "Mensaje sin match,Contenido,2024-01-01,Autor,1000,http://example.com/articulo-filtrado\n"
        )
        uploaded = SimpleUploadedFile(
            "medios.csv",
            content.encode("utf-8"),
            content_type="text/csv",
        )

        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {"archivo": uploaded},
            format="multipart",
        )

        with patch.object(
            IngestionAPIView,
            "forward_payload",
            return_value=Response({"ok": True}, status=202),
        ) as mock_forward:
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        mock_forward.assert_not_called()
        self.assertIn("mensaje", response.data)
        self.assertIn("criterios", response.data["mensaje"])
        self.assertEqual(response.data["duplicados"], 0)
        self.assertEqual(response.data["descartados"], 0)

    def test_construir_payload_forward_usa_tipo_alerta_del_proyecto(self):
        proyecto = SimpleNamespace(id=self.proyecto_id, tipo_alerta="redes")
        registros = [
            {
                "tipo": "articulo",
                "titulo": "Titulo",
                "contenido": "Contenido",
                "fecha": datetime(2024, 1, 1),
                "autor": "Autor",
                "reach": 100,
                "engagement": 5,
                "url": "http://example.com",
                "red_social": "Twitter",
                "datos_adicionales": {"extra": "valor"},
                "proveedor": "medios_twk",
            }
        ]

        view = IngestionAPIView()
        payload = view._construir_payload_forward("medios", registros, proyecto)

        self.assertEqual(payload["proveedor"], "medios_twk")
        self.assertEqual(payload["alertas"][0]["tipo"], "redes")

    @patch("apps.base.api.ingestion.Proyecto")
    def test_registro_manual_usa_tipo_alerta_redes_del_proyecto(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto, tipo_alerta="redes")
        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {
                "proyecto": self.proyecto_id,
                "url": "http://example.com/post",
                "contenido": "Contenido redes",
                "autor": "Usuario",
                "red_social": "https://twitter.com", 
            },
            format="json",
        )

        with patch.object(
            IngestionAPIView,
            "_obtener_usuario_sistema",
            return_value=SimpleNamespace(id=2),
        ), patch.object(
            IngestionAPIView,
            "_crear_articulo",
            side_effect=self._fake_crear_articulo,
        ), patch.object(
            IngestionAPIView,
            "_crear_red_social",
            side_effect=self._fake_crear_red_social,
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(self.ultimo_registro_articulo)
        self.assertIsNotNone(self.ultimo_registro_red)
        self.assertEqual(response.data["listado"][0]["tipo"], "redes")
        self.assertEqual(response.data["duplicados"], 0)
        self.assertEqual(response.data["descartados"], 0)
        self.assertEqual(response.data["mensaje"], "1 registros creados")

    @patch("apps.base.api.ingestion.Proyecto")
    def test_registro_manual_usa_tipo_alerta_medios_del_proyecto(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto, tipo_alerta="medios")
        request = self.factory.post(
            f"/api/ingestion/?proyecto={self.proyecto_id}",
            {
                "proyecto": self.proyecto_id,
                "url": "http://example.com/articulo",
                "titulo": "Titulo articulo",
                "contenido": "Contenido articulo",
                "autor": "Usuario",
                "tipo": "red",
            },
            format="json",
        )

        with patch.object(
            IngestionAPIView,
            "_obtener_usuario_sistema",
            return_value=SimpleNamespace(id=2),
        ), patch.object(
            IngestionAPIView,
            "_crear_articulo",
            side_effect=self._fake_crear_articulo,
        ), patch.object(
            IngestionAPIView,
            "_crear_red_social",
            side_effect=self._fake_crear_red_social,
        ):
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(self.ultimo_registro_articulo)
        self.assertIsNone(self.ultimo_registro_red)
        self.assertEqual(response.data["listado"][0]["tipo"], "medios")
        self.assertEqual(response.data["duplicados"], 0)
        self.assertEqual(response.data["descartados"], 0)
        self.assertEqual(response.data["mensaje"], "1 registros creados")

    def _fake_crear_articulo(self, registro, proyecto, sistema_user):
        self.ultimo_registro_articulo = registro
        return SimpleNamespace(
            id="articulo-id",
            titulo=registro.get("titulo"),
            contenido=registro.get("contenido"),
            fecha_publicacion=registro.get("fecha"),
            autor=registro.get("autor"),
            reach=registro.get("reach"),
            url=registro.get("url"),
        )

    def _fake_crear_red_social(self, registro, proyecto):
        self.ultimo_registro_red = registro
        red_social_nombre = registro.get("red_social")
        red_social = (
            SimpleNamespace(nombre=red_social_nombre)
            if red_social_nombre
            else None
        )
        return SimpleNamespace(
            id="red-id",
            contenido=registro.get("contenido"),
            fecha_publicacion=registro.get("fecha"),
            autor=registro.get("autor"),
            reach=registro.get("reach"),
            engagement=registro.get("engagement"),
            url=registro.get("url"),
            red_social=red_social,
        )


class ObtenerArchivosTests(SimpleTestCase):
    def setUp(self):
        self.view = IngestionAPIView()

    def test_recupera_todos_los_archivos_desde_multivaluedict(self):
        archivo_uno = SimpleUploadedFile(
            "archivo-uno.csv",
            b"contenido uno",
            content_type="text/csv",
        )
        archivo_dos = SimpleUploadedFile(
            "archivo-dos.csv",
            b"contenido dos",
            content_type="text/csv",
        )
        files = MultiValueDict(
            {
                "archivo_principal": [archivo_uno],
                "archivo_secundario": [archivo_dos],
            }
        )
        request = SimpleNamespace(FILES=files)

        archivos = self.view._obtener_archivos(request)

        self.assertEqual(len(archivos), 2)
        self.assertEqual({a.name for a in archivos}, {"archivo-uno.csv", "archivo-dos.csv"})

    def test_recupera_archivos_desde_diccionario_con_listas(self):
        archivo_uno = SimpleUploadedFile(
            "archivo-uno.csv",
            b"contenido uno",
            content_type="text/csv",
        )
        archivo_dos = SimpleUploadedFile(
            "archivo-dos.csv",
            b"contenido dos",
            content_type="text/csv",
        )
        files = {
            "archivo": [archivo_uno],
            "archivo_extra": archivo_dos,
        }
        request = SimpleNamespace(FILES=files)

        archivos = self.view._obtener_archivos(request)

        self.assertEqual(len(archivos), 2)
        self.assertEqual({a.name for a in archivos}, {"archivo-uno.csv", "archivo-dos.csv"})


class FormatearFechaRespuestaTests(SimpleTestCase):
    def test_formatea_fecha_iso_am(self):
        resultado = formatear_fecha_respuesta("2025-09-23T08:00:38.000Z")
        self.assertEqual(resultado, "2025-09-23 08:00:38 AM")

    def test_formatea_fecha_iso_pm(self):
        resultado = formatear_fecha_respuesta("2025-09-23T16:01:38.000Z")
        self.assertEqual(resultado, "2025-09-23 4:01:38 PM")


class IngestionFormatoFechaTests(SimpleTestCase):
    def setUp(self):
        self.view = IngestionAPIView()
        self.proyecto = SimpleNamespace(
            id="123e4567-e89b-12d3-a456-426614174000",
            tipo_alerta="medios",
        )

    def test_construir_payload_forward_formatea_fecha_iso(self):
        registros = [
            {
                "tipo": "articulo",
                "titulo": "Titulo",
                "contenido": "Contenido",
                "fecha": "2025-09-23T16:01:38.000Z",
                "autor": "Autor",
                "reach": 10,
                "engagement": 5,
                "url": "http://example.com",
                "red_social": None,
                "datos_adicionales": {},
                "proveedor": "medios_twk",
            }
        ]

        payload = self.view._construir_payload_forward("medios", registros, self.proyecto)

        self.assertEqual(payload["alertas"][0]["fecha"], "2025-09-23 4:01:38 PM")

    def test_serializar_articulo_usa_formato_legible(self):
        registro = {
            "proveedor": "medios_twk",
            "datos_adicionales": {},
            "fecha": "2025-09-23T08:00:38.000Z",
        }
        articulo = SimpleNamespace(
            id="articulo-id",
            titulo="Titulo",
            contenido="Contenido",
            fecha_publicacion=None,
            autor="Autor",
            reach=10,
            url="http://example.com/articulo",
        )

        resultado = self.view._serializar_articulo(articulo, registro, None)

        self.assertEqual(resultado["fecha"], "2025-09-23 08:00:38 AM")

    def test_serializar_red_usa_formato_legible(self):
        registro = {
            "proveedor": "redes_twk",
            "datos_adicionales": {},
            "fecha": "2025-09-23T16:01:38.000Z",
            "red_social": "twitter.com",
        }
        red = SimpleNamespace(
            id="red-id",
            contenido="Contenido",
            fecha_publicacion=None,
            autor="Autor",
            reach=5,
            engagement=2,
            url="http://example.com/red",
            red_social=None,
        )

        resultado = self.view._serializar_red(red, registro, "red")

        self.assertEqual(resultado["fecha"], "2025-09-23 4:01:38 PM")
