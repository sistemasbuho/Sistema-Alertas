"""Fallback BrightData para completar autor/reach/engagement de redes con
muros de login (Facebook, Instagram, TikTok). Envuelve script/brightdata.py
(el trigger existía; la importación de resultados no estaba cableada)."""

import logging

logger = logging.getLogger(__name__)

# Nombre de red (Redes.red_social.nombre, normalizado) → clave de DATASET_IDS
REDES_SOPORTADAS = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "Youtube",
    "linkedin": "LinkedIn",
    "twitter": "Twitter",
    "x": "Twitter",
}


def completar_red(url, red_social_nombre, *, max_wait_time=120):
    """Devuelve {"autor", "reach", "engagement"} (claves presentes solo si hay
    dato) o {} si BrightData no pudo resolver la URL."""
    from script.brightdata import buscar_interacciones, importar_resultados

    clave = REDES_SOPORTADAS.get((red_social_nombre or "").strip().lower())
    if not clave or not url:
        return {}

    try:
        snapshot_id = buscar_interacciones(url, clave)
        if not snapshot_id:
            return {}
        resultados = importar_resultados(snapshot_id, max_wait_time=max_wait_time)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("BrightData falló para %s: %s", url, exc)
        return {}

    if not resultados:
        return {}

    item = resultados[0]
    datos = {}

    autor = item.get("user_username_raw")
    if autor:
        datos["autor"] = str(autor)

    reach = item.get("page_followers") or item.get("play_count")
    if reach:
        try:
            datos["reach"] = int(reach)
        except (TypeError, ValueError):
            pass

    likes = item.get("likes") or 0
    comentarios = item.get("num_comments") or 0
    compartidos = item.get("num_shares") or 0
    try:
        engagement = int(likes) + int(comentarios) + int(compartidos)
        if engagement:
            datos["engagement"] = engagement
    except (TypeError, ValueError):
        pass

    return datos
