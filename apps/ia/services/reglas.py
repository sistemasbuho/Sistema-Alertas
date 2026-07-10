"""Reglas determinísticas del pipeline IA (nunca las decide el LLM):
semáforo de riesgo, banderas de país, reglas duras no-alertar y confianza."""

import unicodedata

# Mapeo de nombres de país (como aparecen en `ubicacion`) a ISO-2 para la
# regla pais_fuera_lista. Solo países de las mediciones actuales.
PAISES_NOMBRE_ISO = {
    "argentina": "AR", "bolivia": "BO", "brasil": "BR", "brazil": "BR",
    "chile": "CL", "colombia": "CO", "costa rica": "CR", "ecuador": "EC",
    "el salvador": "SV", "guatemala": "GT", "mexico": "MX", "panama": "PA",
    "paraguay": "PY", "peru": "PE", "uruguay": "UY", "venezuela": "VE",
    "canada": "CA", "estados unidos": "US", "usa": "US", "reino unido": "GB",
    "uk": "GB", "espana": "ES", "spain": "ES",
}


def _normalizar(texto):
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in texto if not unicodedata.combining(c)).strip().lower()


def bandera(iso2):
    """Emoji de bandera desde código ISO-3166-1 alpha-2 (🇵🇪, 🇨🇴...)."""
    if not iso2 or not isinstance(iso2, str) or len(iso2) != 2 or not iso2.isalpha():
        return None
    iso2 = iso2.upper()
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2)


def pais_desde_ubicacion(ubicacion):
    """ISO-2 desde un texto de ubicación, o None si no se reconoce."""
    normalizado = _normalizar(ubicacion)
    if not normalizado:
        return None
    if len(normalizado) == 2 and normalizado.isalpha():
        return normalizado.upper()
    for nombre, iso in PAISES_NOMBRE_ISO.items():
        if nombre in normalizado:
            return iso
    return None


def calcular_semaforo(config, *, red_social=None, engagement=None, reach=None, tonalidad=None):
    """Calcula el semáforo según la estrategia configurada en la matriz.

    - "riesgo_engagement_reach" (L'Oréal): bajo=ninguna variable alta,
      medio=una alta, alto=ambas altas.
    - "tonalidad": emoji directo por tonalidad.
    Devuelve {"riesgo", "emoji", "detalle"} o None si no hay config.
    """
    if not config or not config.get("tipo"):
        return None

    tipo = config["tipo"]

    if tipo == "tonalidad":
        emoji = (config.get("emojis") or {}).get(tonalidad)
        return {"riesgo": tonalidad, "emoji": emoji, "detalle": {"tonalidad": tonalidad}}

    if tipo == "riesgo_engagement_reach":
        umbrales_eng = config.get("engagement_alto") or {}
        red = _normalizar(red_social)
        # alias frecuentes
        alias = {"x": "twitter", "fb": "facebook", "ig": "instagram", "tt": "tiktok"}
        red = alias.get(red, red)
        umbral_eng = umbrales_eng.get(red, umbrales_eng.get("default", 500))

        reach_alto_umbral = (config.get("reach_niveles") or {}).get("alto", 8000)

        engagement_alto = engagement is not None and engagement > umbral_eng
        reach_alto = reach is not None and reach > reach_alto_umbral

        if engagement_alto and reach_alto:
            riesgo = "alto"
        elif engagement_alto or reach_alto:
            riesgo = "medio"
        else:
            riesgo = "bajo"

        return {
            "riesgo": riesgo,
            "emoji": (config.get("emojis") or {}).get(riesgo),
            "detalle": {
                "engagement_alto": engagement_alto,
                "reach_alto": reach_alto,
                "umbral_engagement": umbral_eng,
                "umbral_reach_alto": reach_alto_umbral,
            },
        }

    return None


def evaluar_reglas_previas(reglas_no_alertar, alerta, *, paises):
    """Evalúa las reglas con ejecutor='codigo' ANTES de llamar al LLM.

    Devuelve la lista de reglas que descartan la alerta (vacía = pasa).
    Si falta el dato necesario, la regla no aplica (decide IA/humano después).
    """
    aplicadas = []
    for regla in reglas_no_alertar or []:
        if regla.get("ejecutor") != "codigo":
            continue

        tipo = regla.get("tipo")
        if tipo == "min_seguidores":
            # Aproximación documentada: si el proveedor no da seguidores se usa
            # reach como proxy.
            valor = alerta.get("seguidores", alerta.get("reach"))
            minimo = regla.get("valor", 0)
            if valor is not None and valor < minimo:
                aplicadas.append(
                    {"regla": "min_seguidores", "resultado": "descartada", "valor": valor, "minimo": minimo}
                )
        elif tipo == "pais_fuera_lista":
            iso = pais_desde_ubicacion(alerta.get("ubicacion"))
            if iso and paises and iso not in paises:
                aplicadas.append(
                    {"regla": "pais_fuera_lista", "resultado": "descartada", "pais": iso}
                )
    return aplicadas


def calcular_confianza(salida, *, requiere_pais):
    """Confianza global = mínimo de los scores relevantes (conservador y
    explicable: la señal más débil bloquea)."""
    scores = [
        salida.get("relevancia_score") or 0.0,
        salida.get("tonalidad_score") or 0.0,
    ]
    if requiere_pais:
        scores.append(salida.get("pais_score") or 0.0)
    return min(scores)
