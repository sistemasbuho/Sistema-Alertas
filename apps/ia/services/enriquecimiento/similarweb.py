"""Enriquecimiento de reach para medios vía SimilarWeb (visitas por dominio).

Automatiza el uso principal que el equipo hace hoy a mano (C3). El resultado
se cachea por dominio (TTL 7 días) para proteger la cuota de la API.
"""

import logging
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 24 * 7  # 7 días
API_URL = "https://api.similarweb.com/v1/website/{domain}/total-traffic-and-engagement/visits"


def dominio_desde_url(url):
    if not url:
        return None
    try:
        dominio = urlparse(url).netloc.lower()
        return dominio[4:] if dominio.startswith("www.") else dominio or None
    except ValueError:
        return None


def obtener_reach_dominio(url):
    """Visitas mensuales estimadas del dominio, o None si no hay dato/API key."""
    api_key = getattr(settings, "SIMILARWEB_API_KEY", None)
    if not api_key:
        return None

    dominio = dominio_desde_url(url)
    if not dominio:
        return None

    clave_cache = f"sw:{dominio}"
    cacheado = cache.get(clave_cache)
    if cacheado is not None:
        return cacheado or None  # 0 cacheado = "sin dato"

    try:
        respuesta = requests.get(
            API_URL.format(domain=dominio),
            params={"api_key": api_key, "granularity": "monthly", "main_domain_only": "true"},
            timeout=30,
        )
        if respuesta.status_code != 200:
            logger.warning("SimilarWeb %s para %s", respuesta.status_code, dominio)
            cache.set(clave_cache, 0, CACHE_TTL)
            return None
        visitas = respuesta.json().get("visits") or []
        if not visitas:
            cache.set(clave_cache, 0, CACHE_TTL)
            return None
        reach = int(visitas[-1].get("visits") or 0)
        cache.set(clave_cache, reach, CACHE_TTL)
        return reach or None
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("SimilarWeb falló para %s: %s", dominio, exc)
        return None
