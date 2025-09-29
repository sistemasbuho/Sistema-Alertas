"""Utilidades para el módulo de WhatsApp."""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Iterable, List, MutableMapping, Sequence

from django.utils.dateparse import parse_datetime


def _obtener_fecha(alerta: MutableMapping, *, campo_fecha: str, campo_respaldo: str) -> datetime:
    """Obtiene la fecha de la alerta intentando diferentes formatos."""
    valor = alerta.get(campo_fecha) or alerta.get(campo_respaldo)

    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            return valor.replace(tzinfo=dt_timezone.utc)
        return valor

    if isinstance(valor, str) and valor:
        fecha = parse_datetime(valor)
        if fecha:
            if fecha.tzinfo is None:
                return fecha.replace(tzinfo=dt_timezone.utc)
            return fecha
        try:
            return datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            pass

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
