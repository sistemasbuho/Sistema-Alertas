import csv
import io
import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.response import Response
from rest_framework.views import APIView
from django.urls import NoReverseMatch, reverse

from apps.base.models import Articulo, DetalleEnvio, Redes, RedesSociales
from apps.proyectos.models import Proyecto

from .contenido_redes import ajustar_contenido_red_social
from .utils import (
    combinar_fecha_hora,
    filtrar_registros_por_palabras,
    formatear_fecha_respuesta,
    limpiar_texto,
    normalizar_url,
    normalizar_valor_adicional,
    parsear_datetime,
    parsear_entero,
)


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

PROVEEDORES_NOMBRES = {
    "medios": "medios_twk",
    "redes": "redes_twk",
    "determ": "determ",
}

PROVEEDORES_ENDPOINTS = {
    "medios": "medios-alertas-ingestion",
    "redes": "redes-alertas-ingestion",
    "determ": "redes-alertas-ingestion",
}

DOMINIOS_REDES_SOCIALES = {
    "facebook.com": "Facebook",
    "twitter.com": "Twitter",
    "instagram.com": "Instagram",
    "tiktok.com": "TikTok",
    "youtube.com": "YouTube",
}

CAMPOS_PRINCIPALES = {
    "medios": COLUMNAS_MEDIOS_TWK | {"url", "link"},
    "redes": COLUMNAS_REDES_TWK | {"url", "link", "red_social"},
    "determ": COLUMNAS_DETERM | {"url", "social_network"},
}


class IngestionAPIView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        proyecto = self._obtener_proyecto(request)
        if proyecto is None:
            return Response({"detail": "Proyecto no encontrado o no indicado."}, status=400)

        tipo_alerta_proyecto = self._obtener_tipo_alerta_proyecto(proyecto)
        registros_estandar, proveedor, error_response = self._extraer_registros_estandar(
            request,
            tipo_alerta_proyecto,
        )
        if error_response:
            return error_response

        registros_filtrados = self._filtrar_por_criterios(registros_estandar, proyecto)

        if not registros_filtrados:
            respuesta = self._construir_respuesta_sin_registros(
                proveedor,
                proyecto,
            )
            self._notificar_ruta_externa(respuesta)
            return Response(respuesta, status=200)

        resultado = self._persistir_registros(registros_filtrados, proyecto)
        respuesta = self._construir_respuesta_exito(
            registros_filtrados,
            resultado,
            proveedor,
            proyecto,
        )

        self._notificar_ruta_externa(respuesta)

        return Response(
            respuesta,
            status=201 if resultado["listado"] else 400,
        )

    def _extraer_registros_estandar(
        self,
        request,
        tipo_alerta_proyecto: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[Response]]:
        registro_manual = self._obtener_registro_manual(request)
        if registro_manual:
            self._ajustar_registro_manual_por_tipo_alerta(
                registro_manual, tipo_alerta_proyecto
            )
            return [registro_manual], registro_manual.get("proveedor"), None

        archivos = self._obtener_archivos(request)
        if not archivos:
            return [], None, Response(
                {"detail": "Se requiere un archivo CSV o XLSX."},
                status=400,
            )

        registros_acumulados: List[Dict[str, Any]] = []
        proveedores_detectados: List[str] = []

        for archivo in archivos:
            extension = os.path.splitext(archivo.name)[1].lower()
            if extension not in {".csv", ".xlsx"}:
                return [], None, Response(
                    {"detail": "Formato de archivo no soportado."},
                    status=400,
                )

            headers, rows = self._parse_file(archivo, extension)
            if not headers:
                return [], None, Response(
                    {"detail": "El archivo no contiene encabezados válidos."},
                    status=400,
                )

            provider = self._detectar_proveedor(headers)
            if not provider:
                return [], None, Response(
                    {
                        "detail": "No fue posible determinar el tipo de datos del archivo.",
                    },
                    status=400,
                )

            registros_estandar = self._mapear_filas(provider, rows)
            if not registros_estandar:
                return [], provider, Response(
                    {"detail": "No se encontraron filas válidas en el archivo."},
                    status=400,
                )

            registros_acumulados.extend(registros_estandar)
            proveedores_detectados.append(provider)

        provider_final: Optional[str] = None
        if proveedores_detectados:
            provider_final = proveedores_detectados[0]
            for proveedor in proveedores_detectados[1:]:
                if proveedor != provider_final:
                    provider_final = "multiple"
                    break

        return registros_acumulados, provider_final, None

    def _construir_respuesta_sin_registros(
        self,
        proveedor: Optional[str],
        proyecto: Proyecto,
    ) -> Dict[str, Any]:
        return {
            "proveedor": proveedor,
            "mensaje": "0 registros cumplen con los criterios de aceptación configurados.",
            "listado": [],
            "errores": [],
            "duplicados": 0,
            "descartados": 0,
            "proyecto_keywords": self._obtener_keywords_proyecto(proyecto),
        }

    def _construir_respuesta_exito(
        self,
        registros_filtrados: List[Dict[str, Any]],
        resultado: Dict[str, List[Dict[str, Any]]],
        proveedor: Optional[str],
        proyecto: Proyecto,
    ) -> Dict[str, Any]:
        proveedor_respuesta = registros_filtrados[0].get("proveedor") or proveedor
        total_creados = len(resultado["listado"])
        duplicados = resultado.get("duplicados", 0)
        descartados = resultado.get("descartados", 0)
        detalles: List[str] = []
        if duplicados:
            detalles.append(f"{duplicados} duplicados")
        if descartados:
            detalles.append(f"{descartados} descartados")

        mensaje = f"{total_creados} registros creados"
        if detalles:
            mensaje = f"{mensaje} ({', '.join(detalles)})"

        return {
            "proveedor": proveedor_respuesta,
            "mensaje": mensaje,
            "listado": resultado["listado"],
            "errores": resultado["errores"],
            "duplicados": duplicados,
            "descartados": descartados,
            "proyecto_keywords": self._obtener_keywords_proyecto(proyecto),
        }

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

    def _obtener_archivos(self, request) -> List[Any]:
        archivos: List[Any] = []
        files = getattr(request, "FILES", None)
        if not files:
            return archivos

        if hasattr(files, "getlist"):
            keys = list(getattr(files, "keys", lambda: [])())  # type: ignore[misc]
            if not keys:
                keys = ["file", "archivo"]

            for key in keys:
                for archivo in files.getlist(key):
                    if archivo:
                        archivos.append(archivo)
        else:
            posibles_claves = set()
            if hasattr(files, "keys"):
                posibles_claves.update(files.keys())  # type: ignore[attr-defined]
            posibles_claves.update({"file", "archivo"})

            for key in posibles_claves:
                archivo = files.get(key)
                if archivo:
                    archivos.append(archivo)

        archivos_unicos: List[Any] = []
        vistos = set()
        for archivo in archivos:
            identificador = id(archivo)
            if identificador in vistos:
                continue
            vistos.add(identificador)
            archivos_unicos.append(archivo)
        return archivos_unicos

    def _obtener_registro_manual(self, request) -> Optional[Dict[str, Any]]:
        data_sources = [request.data, request.POST]
        for data in data_sources:
            if not hasattr(data, "get"):
                continue

            url = normalizar_url(self._obtener_valor_data(data, "url") or self._obtener_valor_data(data, "link"))
            if not url:
                continue

            tipo = (self._obtener_valor_data(data, "tipo") or "articulo").strip().lower()
            if tipo not in {"articulo", "red"}:
                tipo = "articulo"

            fecha_raw = (
                self._obtener_valor_data(data, "fecha")
                or self._obtener_valor_data(data, "published")
                or self._obtener_valor_data(data, "fecha_publicacion")
            )

            registro: Dict[str, Any] = {
                "tipo": tipo,
                "titulo": limpiar_texto(
                    self._obtener_valor_data(data, "titulo")
                    or self._obtener_valor_data(data, "title")
                ),
                "contenido": limpiar_texto(
                    self._obtener_valor_data(data, "contenido")
                    or self._obtener_valor_data(data, "content")
                ),
                "fecha": parsear_datetime(fecha_raw) if fecha_raw else None,
                "autor": limpiar_texto(
                    self._obtener_valor_data(data, "autor")
                    or self._obtener_valor_data(data, "extra_author_attributes.name")
                ),
                "reach": parsear_entero(self._obtener_valor_data(data, "reach")),
                "engagement": parsear_entero(self._obtener_valor_data(data, "engagement")),
                "url": url,
                "red_social": limpiar_texto(
                    self._obtener_valor_data(data, "red_social")
                    or self._obtener_valor_data(data, "social_network")
                ),
                "proveedor": "manual",
                "datos_adicionales": {},
            }

            if registro["tipo"] == "red":
                registro["contenido"] = ajustar_contenido_red_social(
                    registro.get("contenido"), registro.get("red_social")
                )

            adicionales = {}
            for clave, valor in self._iterar_items_data(data):
                if clave in {
                    "url",
                    "link",
                    "proyecto",
                    "proyecto_id",
                    "tipo",
                    "titulo",
                    "title",
                    "contenido",
                    "content",
                    "fecha",
                    "published",
                    "fecha_publicacion",
                    "autor",
                    "extra_author_attributes.name",
                    "reach",
                    "engagement",
                    "red_social",
                    "social_network",
                }:
                    continue
                valor_normalizado = normalizar_valor_adicional(valor)
                if valor_normalizado is not None:
                    adicionales[clave] = valor_normalizado

            if adicionales:
                registro["datos_adicionales"] = adicionales

            return registro

        return None

    def _ajustar_registro_manual_por_tipo_alerta(
        self,
        registro: Dict[str, Any],
        tipo_alerta: Optional[str],
    ) -> None:
        if not tipo_alerta:
            return

        tipo_alerta_normalizado = tipo_alerta.strip().lower()
        if not tipo_alerta_normalizado:
            return

        if tipo_alerta_normalizado == "redes":
            registro["tipo"] = "red"
        elif tipo_alerta_normalizado == "medios":
            registro["tipo"] = "articulo"

    def _obtener_valor_data(self, data, key):
        valor = data.get(key)  # type: ignore[attr-defined]
        if isinstance(valor, list):
            return valor[0]
        return valor

    def _iterar_items_data(self, data):
        if hasattr(data, "lists"):
            for clave, valores in data.lists():  # type: ignore[attr-defined]
                if not valores:
                    continue
                yield clave, valores[0] if len(valores) == 1 else valores
        elif hasattr(data, "items"):
            yield from data.items()  # type: ignore[attr-defined]

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

    def _obtener_nombre_proveedor(self, provider: str) -> str:
        return PROVEEDORES_NOMBRES.get(provider, provider)

    def _mapear_filas(self, provider: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if provider == "determ":
            map_function = self._mapear_determ
            campos_principales = CAMPOS_PRINCIPALES.get("determ", set())
            nombre_proveedor = self._obtener_nombre_proveedor("determ")
            registros: List[Dict[str, Any]] = []
            for row in rows:
                registro = map_function(row)
                registro["proveedor"] = nombre_proveedor
                registro["datos_adicionales"] = self._extraer_datos_adicionales(row, campos_principales)
                registros.append(registro)
            return registros

        registros = []
        for row in rows:
            proveedor_inferido = self._inferir_proveedor(row)
            map_function = (
                self._mapear_redes_twk
                if proveedor_inferido == "redes"
                else self._mapear_medios_twk
            )
            campos_principales = CAMPOS_PRINCIPALES.get(proveedor_inferido, set())
            nombre_proveedor = self._obtener_nombre_proveedor(proveedor_inferido)
            registro = map_function(row)
            registro["proveedor"] = nombre_proveedor
            registro["datos_adicionales"] = self._extraer_datos_adicionales(row, campos_principales)
            registros.append(registro)
        return registros

    def _inferir_proveedor(self, row: Dict[str, Any]) -> str:
        if row.get("red_social"):
            return "redes"

        domain_url = row.get("domain_url")
        if domain_url:
            domain_normalized = str(domain_url).lower()
            if any(
                dominio in domain_normalized
                for dominio in DOMINIOS_REDES_SOCIALES.keys()
            ):
                return "redes"

        return "medios"

    def _filtrar_por_criterios(
        self, registros: List[Dict[str, Any]], proyecto: Proyecto
    ) -> List[Dict[str, Any]]:
        criterios: Iterable[str] = []
        if proyecto and hasattr(proyecto, "get_criterios_aceptacion_list"):
            criterios = proyecto.get_criterios_aceptacion_list()
        return filtrar_registros_por_palabras(registros, criterios)

    def _obtener_keywords_proyecto(self, proyecto: Optional[Proyecto]) -> List[str]:
        if not proyecto:
            return []

        if hasattr(proyecto, "get_keywords_list"):
            keywords = proyecto.get_keywords_list()
            if isinstance(keywords, list):
                return keywords

        keywords_attr = getattr(proyecto, "keywords", None)
        if keywords_attr:
            return [
                keyword.strip()
                for keyword in str(keywords_attr).split(",")
                if keyword and keyword.strip()
            ]

        return []

    def _construir_payload_forward(
        self,
        provider: str,
        registros: List[Dict[str, Any]],
        proyecto: Proyecto,
    ) -> Dict[str, Any]:
        proveedor_nombre = registros[0].get("proveedor") or self._obtener_nombre_proveedor(provider)
        tipo_alerta_proyecto = self._obtener_tipo_alerta_proyecto(proyecto)
        alertas = []
        for registro in registros:
            alerta = {
                "tipo": tipo_alerta_proyecto or registro.get("tipo"),
                "titulo": registro.get("titulo"),
                "contenido": registro.get("contenido"),
                "fecha": formatear_fecha_respuesta(registro.get("fecha")),
                "autor": registro.get("autor"),
                "reach": registro.get("reach"),
                "engagement": registro.get("engagement"),
                "url": registro.get("url"),
                "red_social": registro.get("red_social"),
                "datos_adicionales": registro.get("datos_adicionales") or {},
            }
            for campo in ("reach", "engagement"):
                valor = alerta.get(campo)
                if valor is not None and not isinstance(valor, str):
                    alerta[campo] = str(valor)
            alertas.append(alerta)

        return {
            "proveedor": proveedor_nombre,
            "proyecto": str(proyecto.id),
            "alertas": alertas,
        }

    def _mapear_medios_twk(self, row: Dict[str, Any]) -> Dict[str, Any]:
        fecha = parsear_datetime(row.get("published"))
        return {
            "tipo": "articulo",
            "titulo": limpiar_texto(row.get("title")),
            "contenido": limpiar_texto(row.get("content")),
            "fecha": fecha,
            "autor": limpiar_texto(row.get("extra_author_attributes.name")),
            "reach": parsear_entero(row.get("reach")),
            "url": normalizar_url(row.get("url") or row.get("link")),
        }

    def _mapear_redes_twk(self, row: Dict[str, Any]) -> Dict[str, Any]:
        fecha = parsear_datetime(row.get("published"))
        red_social = limpiar_texto(row.get("domain_url"))
        contenido = ajustar_contenido_red_social(
            limpiar_texto(row.get("content")),
            red_social,
        )
        return {
            "tipo": "red",
            "contenido": contenido,
            "fecha": fecha,
            "autor": limpiar_texto(row.get("extra_author_attributes.name")),
            "reach": parsear_entero(row.get("reach")),
            "engagement": parsear_entero(row.get("engagement")),
            "url": normalizar_url(row.get("url") or row.get("link")),
            "red_social": red_social,
        }

    def _mapear_determ(self, row: Dict[str, Any]) -> Dict[str, Any]:
        fecha = combinar_fecha_hora(row.get("date"), row.get("time"))
        red_social = limpiar_texto(row.get("social_network"))
        contenido = ajustar_contenido_red_social(
            limpiar_texto(row.get("mention_snippet")),
            red_social,
        )
        return {
            "tipo": "red",
            "contenido": contenido,
            "fecha": fecha,
            "autor": limpiar_texto(row.get("author")),
            "reach": parsear_entero(row.get("reach")),
            "engagement": parsear_entero(row.get("engagement_rate")),
            "url": normalizar_url(row.get("url")),
            "red_social": red_social,
        }

    # ------------------------------------------------------------------
    # Persistencia y serialización
    # ------------------------------------------------------------------
    def _persistir_registros(self, registros: List[Dict[str, Any]], proyecto: Proyecto) -> Dict[str, List[Dict[str, Any]]]:
        errores: List[Dict[str, Any]] = []
        listado: List[Dict[str, Any]] = []
        duplicados = 0
        descartados = 0
        sistema_user = self._obtener_usuario_sistema()
        tipo_alerta_proyecto = self._obtener_tipo_alerta_proyecto(proyecto)

        for indice, registro in enumerate(registros, start=1):
            try:
                if registro.get("tipo") == "articulo":
                    articulo = self._crear_articulo(registro, proyecto, sistema_user)
                    listado.append(
                        self._serializar_articulo(articulo, registro, tipo_alerta_proyecto)
                    )
                else:
                    red = self._crear_red_social(registro, proyecto)
                    listado.append(
                        self._serializar_red(red, registro, tipo_alerta_proyecto)
                    )
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Error procesando fila %s", indice)
                mensaje_error = str(exc)
                if isinstance(exc, ValueError) and "ya existe" in mensaje_error.lower():
                    duplicados += 1
                else:
                    descartados += 1
                errores.append({"fila": indice, "error": mensaje_error})
        return {
            "listado": listado,
            "errores": errores,
            "duplicados": duplicados,
            "descartados": descartados,
        }

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

            DetalleEnvio.objects.create(
                estado_enviado=False,
                estado_revisado=False,
                medio=articulo,
                proyecto=proyecto,
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
                domain_parse = urlparse(nombre_red)
                domain_candidate = (domain_parse.netloc or domain_parse.path or "").lower()
                if domain_candidate.startswith("www."):
                    domain_candidate = domain_candidate[4:]

                candidate_names: List[str] = []
                if domain_candidate:
                    for dominio, nombre in DOMINIOS_REDES_SOCIALES.items():
                        dominio_normalizado = dominio.lower()
                        if dominio_normalizado.startswith("www."):
                            dominio_normalizado = dominio_normalizado[4:]
                        dominio_base = dominio_normalizado.split(".")[0]
                        if dominio_normalizado and dominio_normalizado in domain_candidate:
                            candidate_names.append(nombre)
                        elif dominio_base and dominio_base in domain_candidate:
                            candidate_names.append(nombre)

                candidate_names.extend(
                    [
                        domain_candidate,
                        domain_candidate.split(".")[0] if domain_candidate else "",
                        str(nombre_red).strip(),
                    ]
                )

                for nombre_candidato in dict.fromkeys(
                    valor for valor in candidate_names if valor
                ):
                    red_social_obj = RedesSociales.objects.filter(
                        nombre__iexact=nombre_candidato
                    ).first()
                    if red_social_obj:
                        break

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

            DetalleEnvio.objects.create(
                estado_enviado=False,
                estado_revisado=False,
                red_social=red,
                proyecto=proyecto,
            )
        return red

    def _serializar_articulo(
        self,
        articulo: Articulo,
        registro: Dict[str, Any],
        tipo_alerta: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "id": str(articulo.id),
            "tipo": (tipo_alerta or "articulo"),
            "titulo": articulo.titulo,
            "contenido": articulo.contenido,
            "fecha": formatear_fecha_respuesta(articulo.fecha_publicacion),
            "autor": articulo.autor,
            "reach": articulo.reach,
            "engagement": None,
            "url": articulo.url,
            "red_social": None,
            "proveedor": registro.get("proveedor"),
            "datos_adicionales": registro.get("datos_adicionales") or {},
        }

    def _serializar_red(
        self,
        red: Redes,
        registro: Dict[str, Any],
        tipo_alerta: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "id": str(red.id),
            "tipo": (tipo_alerta or "red"),
            "titulo": None,
            "contenido": red.contenido,
            "fecha": formatear_fecha_respuesta(red.fecha_publicacion),
            "autor": red.autor,
            "reach": red.reach,
            "engagement": red.engagement,
            "url": red.url,
            "red_social": red.red_social.nombre if red.red_social else None,
            "proveedor": registro.get("proveedor"),
            "datos_adicionales": registro.get("datos_adicionales") or {},
        }

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _obtener_tipo_alerta_proyecto(self, proyecto: Optional[Proyecto]) -> Optional[str]:
        if not proyecto:
            return None

        tipo_alerta = getattr(proyecto, "tipo_alerta", None)
        if isinstance(tipo_alerta, str):
            tipo_alerta_normalizado = tipo_alerta.strip()
            if tipo_alerta_normalizado:
                return tipo_alerta_normalizado
        return None

    def _obtener_usuario_sistema(self):
        UserModel = get_user_model()
        try:
            return UserModel.objects.get(id=2)
        except UserModel.DoesNotExist as exc:  # type: ignore[attr-defined]
            raise ValueError("El usuario del sistema (id=2) no existe") from exc

    def _extraer_datos_adicionales(self, row: Dict[str, Any], campos_principales: Iterable[str]) -> Dict[str, Any]:
        campos_base = set(campos_principales)
        adicionales: Dict[str, Any] = {}
        for key, value in row.items():
            if key in campos_base:
                continue
            valor_limpio = normalizar_valor_adicional(value)
            if valor_limpio is not None:
                adicionales[key] = valor_limpio
        return adicionales

    def _notificar_ruta_externa(self, payload: Dict[str, Any]) -> None:
        url = getattr(settings, "RUTA_X_URL", None) or "http://localhost:8000/ruta_x"
        try:
            requests.post(url, json=payload, timeout=5)
        except requests.RequestException as exc:  # pylint: disable=broad-except
            logger.warning("No fue posible notificar la ruta externa %s: %s", url, exc)

    def forward_payload(self, endpoint_name: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None):
        headers = headers.copy() if headers else {}

        if "Authorization" not in headers and getattr(self.request, "META", None):
            auth_header = self.request.META.get("HTTP_AUTHORIZATION")
            if auth_header:
                headers["Authorization"] = auth_header

        try:
            relative_url = reverse(endpoint_name)
        except NoReverseMatch:
            logger.error("No se encontró el endpoint '%s' para reenviar el payload", endpoint_name)
            return Response(
                {"detail": f"Endpoint '{endpoint_name}' no encontrado."},
                status=500,
            )

        forward_base_url = getattr(settings, "INGESTION_FORWARD_BASE_URL", None)
        if forward_base_url:
            base_url = forward_base_url.rstrip("/")
            target_url = f"{base_url}{relative_url}"
        elif getattr(self, "request", None) is not None:
            target_url = self.request.build_absolute_uri(relative_url)
        else:
            default_base = getattr(settings, "DEFAULT_DOMAIN", "http://localhost:8000")
            target_url = f"{default_base.rstrip('/')}{relative_url}"

        timeout = getattr(settings, "INGESTION_FORWARD_TIMEOUT", 10)

        try:
            response = requests.post(
                target_url,
                json=payload,
                headers=headers or None,
                timeout=timeout,
            )
        except requests.RequestException as exc:  # pragma: no cover - network failure handling
            logger.error(
                "Error reenviando payload a '%s': %s",
                target_url,
                exc,
            )
            return Response(
                {"detail": "No fue posible reenviar el payload."},
                status=502,
            )

        try:
            content = response.json()
        except ValueError:
            content = {"detail": response.text or "Respuesta vacía"}

        return Response(content, status=response.status_code)
