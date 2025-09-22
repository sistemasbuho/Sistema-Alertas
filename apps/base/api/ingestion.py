import csv
import io
import logging
import os
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from openpyxl import load_workbook
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.base.models import Articulo, Redes, RedesSociales
from apps.proyectos.models import Proyecto


logger = logging.getLogger(__name__)


COLUMNAS_MEDIOS_TWK = {
    "title",
    "content",
    "published",
    "extra_author_attributes.name",
    "reach",
}

COLUMNAS_REDES_TWK = {
    "content",
    "published",
    "extra_author_attributes.name",
    "reach",
    "engagement",
}

COLUMNAS_DETERM = {
    "mention_snippet",
    "date",
    "time",
    "reach",
    "engagement_rate",
    "author",
}


class IngestionAPIView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        proyecto = self._obtener_proyecto(request)
        if proyecto is None:
            return Response({"detail": "Proyecto no encontrado o no indicado."}, status=400)

        archivo = self._obtener_archivo(request)
        if not archivo:
            return Response({"detail": "Se requiere un archivo CSV o XLSX."}, status=400)

        extension = os.path.splitext(archivo.name)[1].lower()
        if extension not in {".csv", ".xlsx"}:
            return Response({"detail": "Formato de archivo no soportado."}, status=400)

        headers, rows = self._parse_file(archivo, extension)
        if not headers:
            return Response({"detail": "El archivo no contiene encabezados válidos."}, status=400)

        provider = self._detectar_proveedor(headers)
        if not provider:
            return Response({"detail": "No fue posible determinar el tipo de datos del archivo."}, status=400)

        registros_estandar = self._mapear_filas(provider, rows)

        if not registros_estandar:
            return Response({"detail": "No se encontraron filas válidas en el archivo."}, status=400)

        resultado = self._persistir_registros(registros_estandar, proyecto)

        respuesta = {
            "mensaje": f"{len(resultado['listado'])} registros creados",
            "listado": resultado["listado"],
            "errores": resultado["errores"],
        }

        self._notificar_ruta_externa(respuesta)

        return Response(
            respuesta,
            status=201 if resultado["listado"] else 400,
        )

    # ------------------------------------------------------------------
    # Extracción de datos de la request
    # ------------------------------------------------------------------
    def _obtener_proyecto(self, request) -> Optional[Proyecto]:
        posibles_ids: Iterable[str] = (
            request.data.get("proyecto_id"),
            request.data.get("proyecto"),
            request.POST.get("proyecto_id"),
            request.POST.get("proyecto"),
            request.query_params.get("proyecto"),
        )
        proyecto_id = next((pid for pid in posibles_ids if pid), None)
        if not proyecto_id:
            return None
        return Proyecto.objects.filter(id=proyecto_id).first()

    def _obtener_archivo(self, request):
        return request.FILES.get("file") or request.FILES.get("archivo")

    # ------------------------------------------------------------------
    # Procesamiento de archivos
    # ------------------------------------------------------------------
    def _parse_file(self, uploaded_file, extension: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        if extension == ".csv":
            return self._parse_csv(uploaded_file)
        return self._parse_xlsx(uploaded_file)

    def _parse_csv(self, uploaded_file) -> Tuple[List[str], List[Dict[str, Any]]]:
        uploaded_file.seek(0)
        data = uploaded_file.read().decode("utf-8-sig")
        csv_buffer = io.StringIO(data)
        reader = csv.DictReader(csv_buffer)
        headers = [self._normalizar_encabezado(h) for h in (reader.fieldnames or [])]
        rows = []
        for raw_row in reader:
            rows.append({self._normalizar_encabezado(k): v for k, v in raw_row.items()})
        return headers, rows

    def _parse_xlsx(self, uploaded_file) -> Tuple[List[str], List[Dict[str, Any]]]:
        uploaded_file.seek(0)
        workbook = load_workbook(uploaded_file, data_only=True)
        sheet = workbook.active
        rows_iter = sheet.iter_rows(values_only=True)
        try:
            headers_row = next(rows_iter)
        except StopIteration:
            return [], []

        headers = [self._normalizar_encabezado(value) for value in headers_row]
        rows: List[Dict[str, Any]] = []
        for row in rows_iter:
            row_dict: Dict[str, Any] = {}
            for idx, header in enumerate(headers):
                if not header:
                    continue
                row_dict[header] = row[idx] if idx < len(row) else None
            rows.append(row_dict)
        return headers, rows

    def _normalizar_encabezado(self, header_value) -> str:
        if header_value is None:
            return ""
        return str(header_value).strip().lower()

    # ------------------------------------------------------------------
    # Detección y mapeo de filas
    # ------------------------------------------------------------------
    def _detectar_proveedor(self, headers: List[str]) -> str:
        header_set = set(headers)
        if header_set >= COLUMNAS_MEDIOS_TWK:
            return "medios"
        if header_set >= COLUMNAS_REDES_TWK:
            return "redes"
        if header_set >= COLUMNAS_DETERM:
            return "determ"
        return ""

    def _mapear_filas(self, provider: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        mapper = {
            "medios": self._mapear_medios_twk,
            "redes": self._mapear_redes_twk,
            "determ": self._mapear_determ,
        }
        map_function = mapper.get(provider)
        if not map_function:
            return []
        return [map_function(row) for row in rows]

    def _mapear_medios_twk(self, row: Dict[str, Any]) -> Dict[str, Any]:
        fecha = self._parsear_datetime(row.get("published"))
        return {
            "tipo": "articulo",
            "titulo": self._limpiar_texto(row.get("title")),
            "contenido": self._limpiar_texto(row.get("content")),
            "fecha": fecha,
            "autor": self._limpiar_texto(row.get("extra_author_attributes.name")),
            "reach": self._parsear_entero(row.get("reach")),
            "url": self._limpiar_url(row.get("url") or row.get("link")),
        }

    def _mapear_redes_twk(self, row: Dict[str, Any]) -> Dict[str, Any]:
        fecha = self._parsear_datetime(row.get("published"))
        return {
            "tipo": "red",
            "contenido": self._limpiar_texto(row.get("content")),
            "fecha": fecha,
            "autor": self._limpiar_texto(row.get("extra_author_attributes.name")),
            "reach": self._parsear_entero(row.get("reach")),
            "engagement": self._parsear_entero(row.get("engagement")),
            "url": self._limpiar_url(row.get("url") or row.get("link")),
            "red_social": self._limpiar_texto(row.get("red_social")),
        }

    def _mapear_determ(self, row: Dict[str, Any]) -> Dict[str, Any]:
        fecha = self._combinar_fecha_hora(row.get("date"), row.get("time"))
        return {
            "tipo": "red",
            "contenido": self._limpiar_texto(row.get("mention_snippet")),
            "fecha": fecha,
            "autor": self._limpiar_texto(row.get("author")),
            "reach": self._parsear_entero(row.get("reach")),
            "engagement": self._parsear_entero(row.get("engagement_rate")),
            "url": self._limpiar_url(row.get("url")),
            "red_social": self._limpiar_texto(row.get("social_network")),
        }

    # ------------------------------------------------------------------
    # Persistencia y serialización
    # ------------------------------------------------------------------
    def _persistir_registros(self, registros: List[Dict[str, Any]], proyecto: Proyecto) -> Dict[str, List[Dict[str, Any]]]:
        errores: List[Dict[str, Any]] = []
        listado: List[Dict[str, Any]] = []
        sistema_user = self._obtener_usuario_sistema()

        for indice, registro in enumerate(registros, start=1):
            try:
                if registro.get("tipo") == "articulo":
                    articulo = self._crear_articulo(registro, proyecto, sistema_user)
                    listado.append(self._serializar_articulo(articulo))
                else:
                    red = self._crear_red_social(registro, proyecto)
                    listado.append(self._serializar_red(red))
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Error procesando fila %s", indice)
                errores.append({"fila": indice, "error": str(exc)})
        return {"listado": listado, "errores": errores}

    def _crear_articulo(self, registro: Dict[str, Any], proyecto: Proyecto, sistema_user) -> Articulo:
        with transaction.atomic():
            url = registro.get("url") or ""
            if url and Articulo.objects.filter(url=url, proyecto=proyecto).exists():
                raise ValueError("La URL ya existe para este proyecto")

            articulo = Articulo.objects.create(
                titulo=registro.get("titulo"),
                contenido=registro.get("contenido"),
                url=url,
                fecha_publicacion=registro.get("fecha") or timezone.now(),
                autor=registro.get("autor"),
                reach=registro.get("reach"),
                proyecto=proyecto,
                created_by=sistema_user,
            )
        return articulo

    def _crear_red_social(self, registro: Dict[str, Any], proyecto: Proyecto) -> Redes:
        with transaction.atomic():
            url = registro.get("url") or ""
            if url and Redes.objects.filter(url=url, proyecto=proyecto).exists():
                raise ValueError("La URL ya existe para este proyecto")

            red_social_obj = None
            nombre_red = registro.get("red_social")
            if nombre_red:
                red_social_obj = RedesSociales.objects.filter(nombre__iexact=nombre_red).first()

            red = Redes.objects.create(
                contenido=registro.get("contenido"),
                fecha_publicacion=registro.get("fecha") or timezone.now(),
                url=url,
                autor=registro.get("autor"),
                reach=registro.get("reach"),
                engagement=registro.get("engagement"),
                red_social=red_social_obj,
                proyecto=proyecto,
            )
        return red

    def _serializar_articulo(self, articulo: Articulo) -> Dict[str, Any]:
        return {
            "id": str(articulo.id),
            "tipo": "articulo",
            "titulo": articulo.titulo,
            "contenido": articulo.contenido,
            "fecha": self._formatear_fecha_respuesta(articulo.fecha_publicacion),
            "autor": articulo.autor,
            "reach": articulo.reach,
            "engagement": None,
            "url": articulo.url,
            "red_social": None,
        }

    def _serializar_red(self, red: Redes) -> Dict[str, Any]:
        return {
            "id": str(red.id),
            "tipo": "red",
            "titulo": None,
            "contenido": red.contenido,
            "fecha": self._formatear_fecha_respuesta(red.fecha_publicacion),
            "autor": red.autor,
            "reach": red.reach,
            "engagement": red.engagement,
            "url": red.url,
            "red_social": red.red_social.nombre if red.red_social else None,
        }

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _obtener_usuario_sistema(self):
        UserModel = get_user_model()
        try:
            return UserModel.objects.get(id=2)
        except UserModel.DoesNotExist as exc:  # type: ignore[attr-defined]
            raise ValueError("El usuario del sistema (id=2) no existe") from exc

    def _parsear_datetime(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return self._asegurar_timezone(value)
        if isinstance(value, date):
            return self._asegurar_timezone(datetime.combine(value, time.min))
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            # Excel puede entregar fechas como números
            base_date = datetime(1899, 12, 30)
            return self._asegurar_timezone(base_date + timedelta(days=float(value)))
        parsed = parse_datetime(str(value))
        if parsed:
            return self._asegurar_timezone(parsed)
        parsed_date = parse_date(str(value))
        if parsed_date:
            return self._asegurar_timezone(datetime.combine(parsed_date, time.min))
        parsed_time = parse_time(str(value))
        if parsed_time:
            return self._asegurar_timezone(datetime.combine(timezone.now().date(), parsed_time))
        return None

    def _combinar_fecha_hora(self, fecha_value: Any, hora_value: Any) -> Optional[datetime]:
        fecha = None
        if isinstance(fecha_value, datetime):
            fecha = fecha_value
        elif isinstance(fecha_value, date):
            fecha = datetime.combine(fecha_value, time.min)
        elif fecha_value not in (None, ""):
            fecha = self._parsear_datetime(fecha_value)

        hora = None
        if isinstance(hora_value, datetime):
            hora = hora_value.time()
        elif isinstance(hora_value, time):
            hora = hora_value
        elif hora_value not in (None, ""):
            hora = parse_time(str(hora_value))

        if fecha and hora:
            fecha = fecha.replace(hour=hora.hour, minute=hora.minute, second=hora.second, microsecond=hora.microsecond)
        return self._asegurar_timezone(fecha) if fecha else None

    def _asegurar_timezone(self, value: datetime) -> datetime:
        if value is None:
            return None
        if timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_current_timezone())
        return value

    def _parsear_entero(self, value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            if isinstance(value, str):
                value = value.replace(",", "").strip()
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _limpiar_texto(self, value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        return str(value).strip()

    def _limpiar_url(self, value: Any) -> Optional[str]:
        valor = self._limpiar_texto(value)
        if not valor:
            return None
        return valor

    def _formatear_fecha_respuesta(self, value: Optional[datetime]) -> Optional[str]:
        if not value:
            return None
        return value.astimezone(timezone.get_current_timezone()).isoformat()

    def _notificar_ruta_externa(self, payload: Dict[str, Any]) -> None:
        url = getattr(settings, "RUTA_X_URL", None) or "http://localhost:8000/ruta_x"
        try:
            requests.post(url, json=payload, timeout=5)
        except requests.RequestException as exc:  # pylint: disable=broad-except
            logger.warning("No fue posible notificar la ruta externa %s: %s", url, exc)
