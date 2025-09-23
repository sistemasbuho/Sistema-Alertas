from __future__ import annotations
from typing import Optional

_TWITTER_NAMES = {"twitter", "x", "http://twitter.com/"}
_KEYWORDS = ("QT", "Repost", "qt")


def ajustar_contenido_red_social(contenido: Optional[str], red_social: Optional[str]) -> Optional[str]:
    """Mantiene el contenido antes de la QT (incluyendo la QT misma), sin modificar mayúsculas/minúsculas."""
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
    recorte = texto[:indice + longitud].strip()
    
    return recorte
