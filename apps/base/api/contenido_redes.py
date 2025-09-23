"""Utilidades para el procesamiento de contenido de redes sociales."""
from __future__ import annotations

from typing import Optional


_TWITTER_NAMES = {"Twitter", "x"}
_KEYWORDS = ("QT", "Repost")


def ajustar_contenido_red_social(contenido: Optional[str], red_social: Optional[str]) -> Optional[str]:
    """Recorta el contenido cuando corresponde a publicaciones de Twitter/X con QT o Repost."""
    if not contenido:
        return contenido

    red = (red_social or "").strip().lower()
    if red not in _TWITTER_NAMES:
        return contenido.strip()

    texto = contenido
    texto_normalizado = texto.upper()
    cortes = []

    for palabra in _KEYWORDS:
        indice = texto_normalizado.find(palabra.upper())
        if indice != -1:
            cortes.append((indice, len(palabra)))

    if not cortes:
        return texto.strip()

    indice, longitud = min(cortes, key=lambda item: item[0])
    return texto[: indice + longitud].strip()
