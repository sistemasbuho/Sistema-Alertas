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

    def _mock_proyecto(self, mock_proyecto, criterios=None):
        criterios = criterios or []
        proyecto = SimpleNamespace(
            id=self.proyecto_id,
            get_criterios_aceptacion_list=lambda: criterios,
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
            "forward_payload",
            return_value=Response({"ok": True}, status=202),
        ) as mock_forward:
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 202)
        mock_forward.assert_called_once()
        endpoint_name, payload, _ = mock_forward.call_args[0]
        self.assertEqual(endpoint_name, "medios-alertas-ingestion")
        self.assertEqual(payload["proveedor"], "medios_twk")
        self.assertEqual(payload["proyecto"], self.proyecto_id)
        self.assertEqual(len(payload["alertas"]), 1)
        self.assertEqual(payload["alertas"][0]["autor"], "Autor")

    @patch("apps.base.api.ingestion.Proyecto")
    def test_detects_redes_twk_from_xlsx_and_forwards_payload(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
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
            ]
        )
        sheet.append(["Hola", "2024-02-02", "User", "500", "42"])
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
            "forward_payload",
            return_value=Response({"ok": True}, status=201),
        ) as mock_forward:
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        mock_forward.assert_called_once()
        endpoint_name, payload, _ = mock_forward.call_args[0]
        self.assertEqual(endpoint_name, "redes-alertas-ingestion")
        self.assertEqual(payload["proveedor"], "redes_twk")
        self.assertEqual(len(payload["alertas"]), 1)
        alerta = payload["alertas"][0]
        self.assertEqual(alerta["contenido"], "Hola")
        self.assertEqual(alerta["engagement"], "42")

    @patch("apps.base.api.ingestion.Proyecto")
    def test_redes_twk_trim_contenido_for_twitter_qt(self, mock_proyecto):
        self._mock_proyecto(mock_proyecto)
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
            "forward_payload",
            return_value=Response({"ok": True}, status=201),
        ) as mock_forward:
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        mock_forward.assert_called_once()
        alerta = mock_forward.call_args[0][1]["alertas"][0]
        self.assertEqual(alerta["contenido"], "Mensaje inicial QT")
        self.assertEqual(alerta["red_social"], "Twitter")

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
            "forward_payload",
            return_value=Response({"ok": True}, status=202),
        ) as mock_forward:
            response = IngestionAPIView.as_view()(request)

        self.assertEqual(response.status_code, 202)
        mock_forward.assert_called_once()
        payload = mock_forward.call_args[0][1]
        self.assertEqual(len(payload["alertas"]), 1)
        self.assertEqual(payload["alertas"][0]["titulo"], "Alerta importante")

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
        self.assertIn("detail", response.data)
        self.assertIn("criterios", response.data["detail"])
