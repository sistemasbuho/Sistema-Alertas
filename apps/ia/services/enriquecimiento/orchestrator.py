"""Orquestador del completado de datos faltantes (Epic C).

Invariantes:
- SOLO llena campos vacíos (C4: el desfase de engagement no se corrige nunca).
- reach == 0 se considera faltante-sospechoso (C1: "un reach en cero hace ruido").
- Cada campo completado queda auditado en EnriquecimientoLog y el resumen se
  devuelve para EvaluacionIA.datos_completados.

Precedencia por campo:
- Redes FB/IG/TikTok: BrightData (muros de login) → ScrapeGraphAI
- Redes X/YouTube/otras: ScrapeGraphAI → BrightData
- Medios titulo/ubicacion: heurística TLD → ScrapeGraphAI
- Medios reach: SimilarWeb
"""

import logging
import time

from apps.ia.models import EnriquecimientoLog
from apps.ia.services import reglas

from . import brightdata, scrapegraph, similarweb

logger = logging.getLogger(__name__)

REACH_CERO_ES_FALTANTE = True

REDES_LOGIN_WALL = {"facebook", "instagram", "tiktok"}

# Sufijos de dominio → país (método humano replicado, C2)
TLD_PAIS = {
    ".co": "Colombia", ".pe": "Perú", ".mx": "México", ".ar": "Argentina",
    ".cl": "Chile", ".ec": "Ecuador", ".bo": "Bolivia", ".uy": "Uruguay",
    ".py": "Paraguay", ".ve": "Venezuela", ".gt": "Guatemala", ".cr": "Costa Rica",
    ".pa": "Panamá", ".sv": "El Salvador", ".br": "Brasil",
}


def _falta(objeto, campo):
    valor = getattr(objeto, campo, None)
    if valor is None or valor == "":
        return True
    if campo == "reach" and REACH_CERO_ES_FALTANTE and valor == 0:
        return True
    return False


def _ubicacion_por_tld(url):
    if not url:
        return None
    dominio = similarweb.dominio_desde_url(url) or ""
    for sufijo, pais in TLD_PAIS.items():
        if dominio.endswith(sufijo):
            return pais
    return None


def _fuentes_para(objeto, tipo, campo):
    """Lista ordenada de (nombre_fuente, callable() -> dict de campos)."""
    url = objeto.url
    if tipo == "redes":
        red = (
            objeto.red_social.nombre.strip().lower()
            if objeto.red_social and objeto.red_social.nombre
            else ""
        )
        bd = ("brightdata", lambda: brightdata.completar_red(url, red))
        sg = ("scrapegraph", lambda: scrapegraph.completar_red(url))
        return [bd, sg] if red in REDES_LOGIN_WALL else [sg, bd]

    # medios
    if campo == "reach":
        return [("similarweb", lambda: {"reach": similarweb.obtener_reach_dominio(url)})]
    if campo == "ubicacion":
        return [
            ("heuristica", lambda: {"ubicacion": _ubicacion_por_tld(url)}),
            ("scrapegraph", lambda: scrapegraph.completar_medio(url)),
        ]
    return [("scrapegraph", lambda: scrapegraph.completar_medio(url))]


def completar(detalle, campos_faltantes):
    """Completa los campos faltantes del Articulo/Redes de un DetalleEnvio.

    Devuelve la lista de {"campo", "fuente", "valor"} completados.
    """
    objeto = detalle.red_social or detalle.medio
    if objeto is None:
        return []

    tipo = "redes" if detalle.red_social_id else "medios"
    completados = []
    resultados_fuente = {}  # cache: una llamada por fuente aunque cubra varios campos

    for campo in campos_faltantes:
        if campo == "pais":  # lo resuelve la IA/humano, no el scraping directo
            continue
        if not _falta(objeto, campo):
            continue

        for nombre_fuente, obtener in _fuentes_para(objeto, tipo, campo):
            inicio = time.monotonic()
            if nombre_fuente not in resultados_fuente:
                try:
                    resultados_fuente[nombre_fuente] = obtener() or {}
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning("Fuente %s falló: %s", nombre_fuente, exc)
                    resultados_fuente[nombre_fuente] = {}
            datos = resultados_fuente[nombre_fuente]
            valor = datos.get(campo)
            latencia_ms = int((time.monotonic() - inicio) * 1000)

            if valor in (None, "", 0):
                continue

            EnriquecimientoLog.objects.create(
                detalle_envio=detalle,
                campo=campo,
                valor_anterior=str(getattr(objeto, campo, None)),
                valor_nuevo=str(valor),
                fuente=nombre_fuente,
                exito=True,
                latencia_ms=latencia_ms,
            )
            setattr(objeto, campo, valor)
            completados.append({"campo": campo, "fuente": nombre_fuente, "valor": valor})
            break
        else:
            EnriquecimientoLog.objects.create(
                detalle_envio=detalle,
                campo=campo,
                valor_anterior=str(getattr(objeto, campo, None)),
                fuente="ninguna",
                exito=False,
                error="Ninguna fuente devolvió el dato",
            )

    if completados:
        objeto.save()
    return completados
