"""Utilidades comunes para la aplicación base."""

from __future__ import annotations

from typing import Dict, Iterable, Optional

from django.db import models


def generar_plantilla_desde_modelo(
    model: type[models.Model],
    campos_excluir: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, object]]:
    """Genera una configuración de plantilla a partir de un modelo.

    Parameters
    ----------
    model:
        Clase del modelo de Django del cual se obtendrán los campos.
    campos_excluir:
        Colección de nombres de campos que se deben omitir en la plantilla.

    Returns
    -------
    dict
        Diccionario donde las claves son los nombres de los campos y los
        valores contienen la información de orden y estilo utilizada por la
        configuración de plantillas.
    """

    campos_excluir = set(campos_excluir or [])

    campos_config: Dict[str, Dict[str, object]] = {}
    indice = 1

    for field in model._meta.get_fields():
        if not getattr(field, "concrete", False):
            continue
        if getattr(field, "auto_created", False):
            continue
        if field.name in campos_excluir:
            continue

        campos_config[field.name] = {"orden": indice, "estilo": {}}
        indice += 1

    return campos_config

