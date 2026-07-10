"""Extracción de datos con ScrapeGraphAI (https://github.com/ScrapeGraphAI/Scrapegraph-ai).

Scraping dirigido por LLM (mismo Gemini/credenciales del pipeline) sobre
Playwright. SOLO debe ejecutarse en el worker `enrich` (imagen
Dockerfile.enrich con Chromium); por eso todos los imports son lazy.

Estado: integración base para el spike (C3). La precisión por tipo de fuente
debe validarse con URLs reales antes de confiar en cada campo (informe
go/no-go por fuente).
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _config():
    return {
        "llm": {
            "model": f"google_vertexai/{settings.GEMINI_MODEL}",
            "temperature": 0,
        },
        "verbose": False,
        "headless": True,
    }


def _ejecutar(prompt, url):
    try:
        from scrapegraphai.graphs import SmartScraperGraph  # import lazy: solo worker enrich
    except ImportError:
        logger.info("scrapegraphai no instalado en este worker; se omite la fuente")
        return None

    try:
        grafo = SmartScraperGraph(prompt=prompt, source=url, config=_config())
        return grafo.run()
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("ScrapeGraphAI falló para %s: %s", url, exc)
        return None


def completar_red(url):
    """Autor/reach/engagement desde un post público de red social."""
    resultado = _ejecutar(
        "Extrae del post: autor (nombre de usuario de quien publica), reach "
        "(seguidores del autor o vistas del post, entero) y engagement (suma de "
        "likes + comentarios + compartidos, entero). Devuelve JSON con claves "
        "autor, reach, engagement; usa null si un dato no está visible.",
        url,
    )
    return _limpiar(resultado, {"autor": str, "reach": int, "engagement": int})


def completar_medio(url):
    """Titular y ubicación (país del medio) desde un artículo de prensa."""
    resultado = _ejecutar(
        "Extrae del artículo: titulo (titular principal) y ubicacion (país del "
        "medio de comunicación; búscalo en la sección 'acerca de', el pie de "
        "página, el dominio o el contexto). Devuelve JSON con claves titulo y "
        "ubicacion; usa null si no es claro.",
        url,
    )
    return _limpiar(resultado, {"titulo": str, "ubicacion": str})


def _limpiar(resultado, esquema):
    if not isinstance(resultado, dict):
        return {}
    datos = {}
    for campo, tipo in esquema.items():
        valor = resultado.get(campo)
        if valor in (None, "", "null", "NA", "N/A"):
            continue
        try:
            datos[campo] = tipo(valor)
        except (TypeError, ValueError):
            continue
    return datos
