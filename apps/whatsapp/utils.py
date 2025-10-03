"""Utilidades para el módulo de WhatsApp."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timezone as dt_timezone
from typing import Iterable, List, MutableMapping, Sequence

from django.utils.dateparse import parse_date, parse_datetime, parse_time

_AM_PM_PATTERN = re.compile(r"\b([ap])(?:\s*\.)?\s*m(?:\s*\.)?\b", re.IGNORECASE)


def _normalizar_indicador_12h(texto: str) -> str:
    """Normaliza indicadores ``AM``/``PM`` escritos con variantes comunes."""

    resultado = _AM_PM_PATTERN.sub(lambda match: match.group(1).upper() + "M", texto)
    return resultado.replace("AM.", "AM").replace("PM.", "PM")


def _parse_datetime_value(valor: object) -> datetime | None:
    """Parses a value into a timezone-aware ``datetime`` when possible."""

    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            return valor.replace(tzinfo=dt_timezone.utc)
        return valor

    if isinstance(valor, date):
        return datetime.combine(valor, time.min).replace(tzinfo=dt_timezone.utc)

    if isinstance(valor, str):
        texto = valor.strip()
        if texto:
            texto_normalizado = _normalizar_indicador_12h(texto)

            fecha = parse_datetime(texto_normalizado)
            if fecha:
                if fecha.tzinfo is None:
                    return fecha.replace(tzinfo=dt_timezone.utc)
                return fecha

            fecha = parse_date(texto_normalizado)
            if fecha:
                return datetime.combine(fecha, time.min).replace(tzinfo=dt_timezone.utc)

            try:
                fecha = datetime.fromisoformat(texto_normalizado.replace("Z", "+00:00"))
            except ValueError:
                fecha = None
            if fecha:
                if fecha.tzinfo is None:
                    return fecha.replace(tzinfo=dt_timezone.utc)
                return fecha

            formatos_12h = ("%Y-%m-%d %I:%M:%S %p", "%Y-%m-%d %I:%M %p")
            for formato in formatos_12h:
                try:
                    fecha = datetime.strptime(texto_normalizado, formato)
                except ValueError:
                    continue
                return fecha.replace(tzinfo=dt_timezone.utc)

    return None


def _parse_time_value(valor: object) -> time | None:
    """Parses a value into a ``time`` instance when possible."""

    if isinstance(valor, time):
        return valor

    if isinstance(valor, datetime):
        return valor.time()

    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return None

        texto_normalizado = _normalizar_indicador_12h(texto)

        parsed = parse_time(texto_normalizado)
        if parsed:
            return parsed

        for formato in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
            try:
                return datetime.strptime(texto_normalizado, formato).time()
            except ValueError:
                continue

    return None


def _obtener_fecha(
    alerta: MutableMapping,
    *,
    campo_fecha: str,
    campo_respaldo: str,
    campos_hora: Sequence[str] = ("hora_publicacion", "hora", "time"),
) -> datetime:
    """Obtiene la fecha de la alerta intentando diferentes formatos."""

    valor_fecha = alerta.get(campo_fecha)
    if not valor_fecha:
        valor_fecha = alerta.get(campo_respaldo)

    fecha = _parse_datetime_value(valor_fecha)

    hora_valor = next((alerta.get(campo) for campo in campos_hora if alerta.get(campo)), None)
    if hora_valor is not None:
        hora = _parse_time_value(hora_valor)
        if hora is not None:
            base = fecha or datetime.min.replace(tzinfo=dt_timezone.utc)
            return base.replace(
                hour=hora.hour,
                minute=hora.minute,
                second=hora.second,
                microsecond=hora.microsecond,
            )

    if fecha is not None:
        return fecha

    return datetime.min.replace(tzinfo=dt_timezone.utc)


def ordenar_alertas_por_fecha(
    alertas: Sequence[MutableMapping] | Iterable[MutableMapping],
    *,
    campo_fecha: str = "fecha_publicacion",
    campo_respaldo: str = "fecha",
) -> List[MutableMapping]:
    """Devuelve las alertas ordenadas de la más antigua a la más reciente."""

    alertas_lista = list(alertas or [])

    return sorted(
        alertas_lista,
        key=lambda alerta: _obtener_fecha(alerta, campo_fecha=campo_fecha, campo_respaldo=campo_respaldo),
    )
