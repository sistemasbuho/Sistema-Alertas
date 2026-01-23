from __future__ import annotations
import re
from typing import Optional

_TWITTER_NAMES = {"twitter", "x", "http://twitter.com/"}
_KEYWORDS = ("QT", "Repost", "qt")


def ajustar_contenido_red_social(contenido: Optional[str], red_social: Optional[str]) -> Optional[str]:
    """Mantiene el contenido antes de la QT (incluyendo la QT misma), sin modificar mayúsculas/minúsculas."""
    if not contenido:
        return contenido

    # Reemplazar saltos de línea con espacios
    texto_limpio = re.sub(r"[\r\n\v\f]+", " ", contenido)
    texto_limpio = re.sub(r"\s+", " ", texto_limpio).strip()

    red = (red_social or "").strip().lower()
    if red not in _TWITTER_NAMES:
        return texto_limpio

    texto_normalizado = texto_limpio.upper()
    cortes = []

    for palabra in _KEYWORDS:
        indice = texto_normalizado.find(palabra.upper())
        if indice != -1:
            cortes.append((indice, len(palabra)))

    if not cortes:
        return texto_limpio

    indice, longitud = min(cortes, key=lambda item: item[0])
    recorte = texto_limpio[:indice + longitud].strip()

    return recorte
