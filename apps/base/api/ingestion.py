import csv
import io
import os
from datetime import date, datetime, time
from typing import Dict, List, Tuple

from django.urls import resolve, reverse
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from openpyxl import load_workbook

from apps.proyectos.models import Proyecto


columnas_medios_twk = {
    "title",
    "content",
    "published",
    "extra_author_attributes.name",
    "reach",
}

columnas_redes_twk = {
    "content",
    "published",
    "extra_author_attributes.name",
    "reach",
    "engagement",
}

columnas_determ = {
    "MENTION_SNIPPET",
    "DATE",
    "TIME",
    "REACH",
    "ENGAGEMENT_RATE",
    "AUTHOR",
}


class IngestionAPIView(APIView):
    authentication_classes: list = []
    permission_classes: list = []
    provider_endpoints = {
        "medios_twk": "medios-alertas-ingestion",
        "redes_twk": "redes-alertas-ingestion",
        "determ": "redes-alertas-ingestion",
    }

    def post(self, request):

        proyecto_id = request.query_params.get("proyecto")
        if not proyecto_id:
            return Response({"detail": "Se requiere el parámetro 'proyecto'."}, status=400)

        proyecto = Proyecto.objects.filter(id=proyecto_id).first()
        if not proyecto:
            return Response({"detail": "Proyecto no encontrado."}, status=404)

        if "file" not in request.FILES and "archivo" not in request.FILES:
            return Response({"detail": "Se requiere un archivo."}, status=400)

        archivo = request.FILES.get("file") or request.FILES.get("archivo")

        extension = os.path.splitext(archivo.name)[1].lower()
        if extension not in {".csv", ".xlsx"}:
            return Response({"detail": "Formato de archivo no soportado."}, status=400)

        headers, rows = self._parse_file(archivo, extension)
        if not headers:
            return Response({"detail": "El archivo no contiene encabezados."}, status=400)

        provider = self._detect_provider(headers)
        if not provider:
            return Response({"detail": "Encabezados no reconocidos para ningún proveedor."}, status=400)

        alertas = self._map_rows(provider, rows)

        payload = {
            "proveedor": provider,
            "proyecto": str(proyecto.id),
            "alertas": alertas,
        }

        endpoint_name = self.provider_endpoints[provider]
        return self.forward_payload(endpoint_name, payload, request)

    def forward_payload(self, endpoint_name: str, payload: Dict, request) -> Response:
        url = reverse(endpoint_name)
        resolver_match = resolve(url)
        view_class = getattr(resolver_match.func, "view_class", None)
        if view_class is None:
            view = resolver_match.func
        else:
            view = view_class.as_view()
        factory = APIRequestFactory()
        internal_request = factory.post(url, payload, format="json")
        internal_request.user = getattr(request, "user", None)
        internal_request.auth = getattr(request, "auth", None)
        internal_request.META.update(request.META)
        response = view(internal_request, *resolver_match.args, **resolver_match.kwargs)
        return response

    def _parse_file(self, uploaded_file, extension: str) -> Tuple[List[str], List[Dict]]:
        if extension == ".csv":
            uploaded_file.seek(0)
            data = uploaded_file.read().decode("utf-8-sig")
            csv_buffer = io.StringIO(data)
            reader = csv.DictReader(csv_buffer)
            headers = reader.fieldnames or []
            rows = [dict(row) for row in reader]
        else:
            uploaded_file.seek(0)
            workbook = load_workbook(uploaded_file, data_only=True)
            sheet = workbook.active
            rows_iter = sheet.iter_rows(values_only=True)
            try:
                headers_row = next(rows_iter)
            except StopIteration:
                return [], []

            headers = [self._normalize_header(value) for value in headers_row]
            rows = []
            for row in rows_iter:
                row_dict = {}
                for idx, header in enumerate(headers):
                    if not header:
                        continue
                    row_dict[header] = row[idx] if idx < len(row) else None
                rows.append(row_dict)
        normalized_headers = [header for header in headers if header]
        return normalized_headers, rows

    def _normalize_header(self, header_value) -> str:
        if header_value is None:
            return ""
        return str(header_value).strip()

    def _detect_provider(self, headers: List[str]) -> str:
        header_set = set(headers)
        if header_set >= columnas_medios_twk:
            return "medios_twk"
        if header_set >= columnas_redes_twk:
            return "redes_twk"
        if header_set >= columnas_determ:
            return "determ"
        return ""

    def _map_rows(self, provider: str, rows: List[Dict]) -> List[Dict]:
        mapper = {
            "medios_twk": self._map_medios_twk,
            "redes_twk": self._map_redes_twk,
            "determ": self._map_determ,
        }
        map_function = mapper.get(provider)
        if not map_function:
            return []
        return [map_function(row) for row in rows]

    def _map_medios_twk(self, row: Dict) -> Dict:
        return {
            "titulo": row.get("title"),
            "contenido": row.get("content"),
            "fecha": row.get("published"),
            "autor": row.get("extra_author_attributes.name"),
            "reach": row.get("reach"),
            "url": row.get("url") or row.get("link"),
        }

    def _map_redes_twk(self, row: Dict) -> Dict:
        return {
            "contenido": row.get("content"),
            "fecha": row.get("published"),
            "autor": row.get("extra_author_attributes.name"),
            "reach": row.get("reach"),
            "engagement": row.get("engagement"),
            "url": row.get("url") or row.get("link"),
            "red_social": row.get("red_social"),
        }

    def _map_determ(self, row: Dict) -> Dict:
        fecha = self._combine_fecha(row.get("DATE"), row.get("TIME"))
        return {
            "contenido": row.get("MENTION_SNIPPET"),
            "fecha": fecha,
            "reach": row.get("REACH"),
            "engagement": row.get("ENGAGEMENT_RATE"),
            "autor": row.get("AUTHOR"),
            "url": row.get("URL"),
            "red_social": row.get("SOCIAL_NETWORK"),
        }

    def _combine_fecha(self, fecha_value, hora_value) -> str:
        fecha_part = self._format_date(fecha_value)
        hora_part = self._format_time(hora_value)
        if fecha_part and hora_part:
            return f"{fecha_part} {hora_part}"
        return fecha_part or hora_part or ""

    def _format_date(self, value) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if value is None:
            return ""
        return str(value)

    def _format_time(self, value) -> str:
        if isinstance(value, datetime):
            return value.time().isoformat()
        if isinstance(value, time):
            return value.isoformat()
        if value is None:
            return ""
        return str(value)
