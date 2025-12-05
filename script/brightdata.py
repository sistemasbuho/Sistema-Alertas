"""Funciones utilitarias para consultas a Bright Data.

Este módulo mantiene únicamente las funciones necesarias para
solicitar y recuperar datos a partir de una URL o identificador de
grupo. Se eliminaron las dependencias de Celery y las operaciones
relacionadas con tareas en segundo plano.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import requests

API_TOKEN = os.getenv("API_TOKEN")

BRIGHTDATA_URL = "https://api.brightdata.com/datasets/v3/trigger"

DATASET_IDS: Dict[str, str] = {
    "LinkedIn": "gd_lyy3tktm25m4avu764",
    "Facebook": "gd_lyclm1571iy3mv57zw",
    "TikTok": "gd_lu702nij2f790tmv9h",
    "Instagram": "gd_lk5ns7kz21pck8jpis",
    "Youtube": "gd_lk56epmy2i5g7lzu0k",
    "LinkedIn_perfiles": "gd_l1viktl72bvl7bjuj0",
    "LinkedIn_compañias": "gd_l1vikfnt1wgvvqz95w",
    "Youtube_perfiles": "gd_lk538t2k2p1k3oos71",
    "Twitter": "gd_lwxkxvnf1cynvib9co",
}


def buscar_interacciones(url: str, red_social: str) -> Optional[str]:
    """Solicita la creación de un snapshot en Bright Data para una URL.

    Args:
        url: Enlace a procesar.
        red_social: Clave de la red social (debe existir en ``DATASET_IDS``).

    Returns:
        Identificador del snapshot generado o ``None`` si ocurre un error.
    """

    dataset = DATASET_IDS.get(red_social)
    if not dataset:
        raise ValueError(f"Red no reconocida: {red_social}")

    headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}
    params: Dict[str, Any] = {
        "dataset_id": dataset,
        "include_errors": "true",
        "columns": [
            "url",
            "user_username_raw",
            "content",
            "date_posted",
            "num_comments",
            "num_shares",
            "num_likes_type",
            "page_followers",
            "likes",
            "play_count",
        ],
        "records_limit": 1,
    }
    urls: List[Dict[str, str]] = [{"url": url}]

    response = requests.post(BRIGHTDATA_URL, headers=headers, params=params, json=urls)
    response.raise_for_status()

    try:
        return response.json().get("snapshot_id")
    except requests.RequestException:
        return None


def importar_resultados(resultado_interacciones: str, *, max_wait_time: int = 120) -> Optional[List[Dict[str, Any]]]:
    """Recupera los resultados de un snapshot desde Bright Data.

    Args:
        resultado_interacciones: Identificador de snapshot retornado por ``buscar_interacciones``.
        max_wait_time: Tiempo máximo de espera en segundos.

    Returns:
        Lista de resultados obtenidos o ``None`` en caso de error o timeout.
    """

    url = f"https://api.brightdata.com/datasets/v3/snapshot/{resultado_interacciones}"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    params = {"format": "json", "compress": "false"}
    start_time = time.time()

    while True:
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return response.json()
            if time.time() - start_time > max_wait_time:
                return None
            time.sleep(10)
        except Exception:
            return None


def exportar_ubicacion(resultado_interacciones: List[Dict[str, Any]], url: str) -> Optional[Any]:
    """Obtiene datos de ubicación asociados a interacciones de LinkedIn.

    Args:
        resultado_interacciones: Lista de interacciones descargadas.
        url: URL original procesada.

    Returns:
        Datos de ubicación si están disponibles, de lo contrario ``None``.
    """

    for interaccion in resultado_interacciones:
        if "use_url" in interaccion:
            identificador_usuario = interaccion["use_url"]
            if "/showcase/" in identificador_usuario or "/company/" in identificador_usuario:
                res = importar_resultados(buscar_interacciones(identificador_usuario, "LinkedIn_compañias"))
                for item in res or []:
                    if "locations" in item and item["locations"]:
                        return item["locations"][0]
                return None
            if "/in/" in identificador_usuario:
                res = importar_resultados(buscar_interacciones(identificador_usuario, "LinkedIn_perfiles"))
                for item in res or []:
                    if "headquarters" in item and item["headquarters"]:
                        return item["headquarters"][0]
                return None
    return None
