from __future__ import annotations

import re

from datetime import date, datetime, time, timedelta
from typing import Iterable as _Iterable
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union
from urllib.parse import urlparse, urlunparse

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time


def limpiar_texto(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    texto = str(value).strip()
    # Eliminar etiquetas <br>, <br/>, <br /> y otras variantes
    texto = re.sub(r"<br\s*/?>", " ", texto, flags=re.IGNORECASE)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto or None


def normalizar_url(value: Any) -> Optional[str]:
    valor = limpiar_texto(value)
    if not valor:
        return None

    parsed = urlparse(valor, scheme="http")

    netloc = parsed.netloc
    path = parsed.path or ""

    if not netloc and parsed.path:
        netloc = parsed.path
        path = ""

    netloc = netloc.rstrip("/")

    if netloc.lower().startswith("www."):
        netloc = netloc[4:]

    scheme = parsed.scheme.lower() if parsed.scheme else "http"
    if scheme != "http":
        scheme = "http"

    path = path.rstrip("/")

    # Limpieza específica para URLs de Instagram
    if "instagram.com" in netloc.lower():
        # Convertir /reel/ y /reels/ a /p/
        path = re.sub(r"/reels?/", "/p/", path)
        # Eliminar parámetros de query
        query = ""
        fragment = ""
    # Limpieza específica para URLs de LinkedIn
    elif "linkedin.com" in netloc.lower():
        # Eliminar parámetros de query (utm_source, utm_medium, rcm, etc.)
        query = ""
        fragment = ""
    else:
        query = parsed.query
        fragment = parsed.fragment

    cleaned = urlunparse(
        (
            scheme,
            netloc,
            path,
            parsed.params,
            query,
            fragment,
        )
    )

    return cleaned or None


def limpiar_url(value: Any) -> Optional[str]:
    """Compatibilidad retroactiva con el nombre anterior de la función."""
    return normalizar_url(value)


def parsear_entero(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None

    try:
        if isinstance(value, str):
            valor_normalizado = value.replace(",", "").strip()
            if not valor_normalizado:
                return None
            if valor_normalizado.endswith("%"):
                valor_normalizado = valor_normalizado[:-1].strip()
            if not valor_normalizado:
                return None
            value = valor_normalizado
        return int(float(value))
    except (TypeError, ValueError):
        return None


def asegurar_timezone(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _parsear_datetime_con_formatos(
    texto: str, formatos: _Iterable[str]
) -> Optional[datetime]:
    for formato in formatos:
        try:
            parsed = datetime.strptime(texto, formato)
        except ValueError:
            continue
        return asegurar_timezone(parsed)
    return None


def _parsear_date_con_formatos(texto: str, formatos: _Iterable[str]) -> Optional[date]:
    for formato in formatos:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def parsear_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return asegurar_timezone(value)
    if isinstance(value, date):
        combined = datetime.combine(value, time.min)
        return asegurar_timezone(combined)
    if isinstance(value, (int, float)):
        # Excel serial numbers use 1899-12-30 as base
        try:
            base_date = datetime(1899, 12, 30)
            combined = base_date + timedelta(days=float(value))
            return asegurar_timezone(combined)
        except (TypeError, ValueError):
            return None
    texto = str(value).strip()
    if not texto:
        return None
    parsed = parse_datetime(texto)
    if parsed:
        return asegurar_timezone(parsed)
    parsed_date = parse_date(texto)
    if parsed_date:
        return asegurar_timezone(datetime.combine(parsed_date, time.min))
    parsed_time = parse_time(texto)
    if parsed_time:
        return asegurar_timezone(datetime.combine(timezone.now().date(), parsed_time))

    formatos_datetime = (
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y",
        "%d-%m-%Y",
    )
    parsed_custom = _parsear_datetime_con_formatos(texto, formatos_datetime)
    if parsed_custom:
        return parsed_custom
    return None


def parsear_fecha(value: Any) -> Optional[date]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    texto = str(value).strip()
    if not texto:
        return None
    parsed = parse_date(texto)
    if parsed:
        return parsed
    formatos_fecha = ("%d/%m/%Y", "%d-%m-%Y")
    return _parsear_date_con_formatos(texto, formatos_fecha)


def parsear_hora(value: Any) -> Optional[time]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, time):
        return value
    texto = str(value).strip()
    if not texto:
        return None
    parsed = parse_time(texto)
    if parsed:
        return parsed

    coincidencias = re.findall(r"\d{1,2}:\d{2}(?::\d{2})?", texto)
    for coincidencia in coincidencias:
        parsed_coincidencia = parse_time(coincidencia)
        if parsed_coincidencia:
            return parsed_coincidencia

    return None


def combinar_fecha_hora(fecha_value: Any, hora_value: Any) -> Optional[datetime]:
    if isinstance(fecha_value, datetime) and isinstance(hora_value, datetime):
        return asegurar_timezone(datetime.combine(fecha_value.date(), hora_value.time()))

    if isinstance(fecha_value, datetime):
        fecha = fecha_value
    else:
        fecha_parsed = parsear_fecha(fecha_value)
        if not fecha_parsed:
            return None
        fecha = datetime.combine(fecha_parsed, time.min)

    hora = parsear_hora(hora_value)
    if not hora:
        return asegurar_timezone(fecha)

    combinado = fecha.replace(
        hour=hora.hour,
        minute=hora.minute,
        second=hora.second,
        microsecond=hora.microsecond,
    )
    return asegurar_timezone(combinado)


def formatear_fecha_respuesta(value: Optional[Union[datetime, str]]) -> Optional[str]:
    if value in (None, ""):
        return None

    fecha: Optional[datetime]
    if isinstance(value, str):
        texto = value.strip()
        if not texto:
            return None
        fecha = parse_datetime(texto)
        if not fecha:
            return texto
    else:
        fecha = value

    fecha_asegurada = asegurar_timezone(fecha)
    if not fecha_asegurada:
        return None

    fecha_local = fecha_asegurada.astimezone(timezone.get_current_timezone())

    hora_24 = fecha_local.hour
    hora_12 = hora_24 % 12 or 12
    if hora_24 < 12 and hora_12 < 10:
        hora_formateada = f"{hora_12:02d}"
    else:
        hora_formateada = str(hora_12)

    minutos = f"{fecha_local.minute:02d}"
    segundos = f"{fecha_local.second:02d}"
    periodo = "AM" if hora_24 < 12 else "PM"

    return f"{fecha_local.strftime('%Y-%m-%d')} {hora_formateada}:{minutos}:{segundos} {periodo}"


def normalizar_valor_adicional(value: Any) -> Optional[Any]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return asegurar_timezone(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, str):
        texto = value.strip()
        return texto or None
    return value


def filtrar_registros_por_palabras(
    registros: Sequence[Dict[str, Any]],
    palabras: Iterable[str],
) -> List[Dict[str, Any]]:
    palabras_normalizadas = [palabra.lower() for palabra in palabras if palabra]
    if not palabras_normalizadas:
        return list(registros)

    filtrados: List[Dict[str, Any]] = []
    for registro in registros:
        titulo = (registro.get("titulo") or "").lower()
        contenido = (registro.get("contenido") or "").lower()
        texto_busqueda = f"{titulo} {contenido}".strip()
        if any(palabra in texto_busqueda for palabra in palabras_normalizadas):
            filtrados.append(registro)
    return filtrados
