from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from apps.base.api.ingestion import IngestionAPIView


class IngestionAPITests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.proyecto_id = "123e4567-e89b-12d3-a456-426614174000"
        self.ultimo_registro_articulo = None
        self.ultimo_registro_red = None

    def _mock_proyecto(self, mock_proyecto, criterios=None, tipo_alerta="medios"):
        criterios = criterios or []
        proyecto = SimpleNamespace(
            id=self.proyecto_id,
            get_criterios_aceptacion_list=lambda: criterios,
            tipo_alerta=tipo_alerta,
        )
        mock_proyecto.objects.filter.return_value.first.return_value = proyecto

    @patch("apps.base.api.ingestion.Proyecto")
    def test_detects_medios_twk_from_csv_and_forwards_payload(self, mock_proyecto):
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
                "red_social",
            ]
        )
        sheet.append(["Hola", "2024-02-02", "User", "500", "42", "Twitter"])
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

    @patch("apps.base.api.ingestion.Proyecto")
    def test_permite_multiples_archivos_en_una_misma_peticion(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
        content_uno = (
            "title,content,published,extra_author_attributes.name,reach\n"
            "Titulo 1,Contenido 1,2024-01-01,Autor 1,1000\n"
        )
        content_dos = (
            "title,content,published,extra_author_attributes.name,reach\n"
            "Titulo 2,Contenido 2,2024-02-02,Autor 2,500\n"
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

    @patch("apps.base.api.ingestion.Proyecto")
    def test_aplica_filtro_de_criterios_de_aceptacion(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto, criterios=["alerta"])
        content = (
            "title,content,published,extra_author_attributes.name,reach\n"
            "Mensaje sin match,Contenido,2024-01-01,Autor,1000\n"
            "Alerta importante,Contenido,2024-01-01,Autor,1000\n"
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

    @patch("apps.base.api.ingestion.Proyecto")
    def test_filtro_de_criterios_sin_coincidencias_no_reenvia(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto, criterios=["alerta"])
        content = (
            "title,content,published,extra_author_attributes.name,reach\n"
            "Mensaje sin match,Contenido,2024-01-01,Autor,1000\n"
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
