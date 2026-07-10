"""Construcción del prompt de clasificación desde la MatrizCliente y schema
de salida estructurada (Pydantic) para Gemini."""

from typing import List, Optional

from pydantic import BaseModel, Field

PROMPT_VERSION = "v1"


class SalidaClasificacion(BaseModel):
    relevante: bool = Field(description="Si la publicación es relevante para el cliente según su matriz")
    relevancia_score: float = Field(ge=0, le=1, description="Certeza de la evaluación de relevancia")
    tonalidad: str = Field(description="Tonalidad según el esquema del cliente")
    tonalidad_score: float = Field(ge=0, le=1)
    categoria_sector: Optional[str] = Field(
        default=None, description="Clave de la categoría de sector aplicable, o null"
    )
    pais: Optional[str] = Field(
        default=None, description="País del contexto de la publicación (ISO-3166-1 alpha-2), o null si no es claro"
    )
    pais_score: float = Field(ge=0, le=1, default=0)
    regla_no_alertar: Optional[str] = Field(
        default=None, description="Clave de la regla no-alertar que aplica, o null"
    )
    marca_detectada: Optional[str] = None
    razones: List[str] = Field(description="2 a 5 razones cortas de la decisión")


def construir_prompt_clasificacion(matriz, alerta, tipo_alerta):
    """Prompt 100% derivado de la matriz digitalizada (A2 consumible por IA)."""
    secciones = []

    secciones.append(
        "Eres el analista de monitoreo de medios y redes sociales de la agencia Buho. "
        "Evalúas si una publicación debe alertarse a un cliente según su matriz de análisis. "
        "Responde únicamente con el JSON del esquema indicado."
    )

    secciones.append(f"## Cliente\n{matriz.descripcion_cliente or matriz.proyecto.nombre}")

    if matriz.menciones_criterio:
        secciones.append(f"## Criterio de relevancia\n{matriz.menciones_criterio}")

    if matriz.marcas:
        secciones.append(
            "## Marcas y menciones a vigilar\n- " + "\n- ".join(matriz.marcas) +
            "\n\nCuidado con colisiones de nombres: un hashtag o texto que contenga el "
            "nombre de una marca pero hable de otra cosa NO es relevante "
            "(ej. un hashtag de campaña ajena que coincide con el nombre de un producto)."
        )

    if matriz.voceros:
        voceros = "\n- ".join(
            f"{v.get('nombre')}" + (f" ({v['notas']})" if v.get("notas") else "")
            for v in matriz.voceros
        )
        secciones.append(f"## Voceros\n- {voceros}")

    tonalidad = matriz.esquema_tonalidad or {}
    escala = tonalidad.get("escala") or ["positivo", "neutral", "negativo"]
    definiciones = tonalidad.get("definiciones") or {}
    lineas = [f"Valores permitidos: {', '.join(escala)}."]
    for valor, definicion in definiciones.items():
        lineas.append(f"- {valor}: {definicion}")
    secciones.append("## Esquema de tonalidad\n" + "\n".join(lineas))

    if matriz.paises:
        secciones.append(
            "## Países de la medición\n"
            f"{', '.join(matriz.paises)} (ISO-3166-1 alpha-2).\n"
            "Infiere el país del CONTEXTO de la publicación (autor, medio, tema, lugar). "
            "Si no es claro, devuelve null en pais con score bajo."
        )

    if matriz.criterios_sector:
        lineas = [
            f"- {c.get('clave')}: {c.get('descripcion')}" for c in matriz.criterios_sector
        ]
        secciones.append(
            "## Categorías de sector\nSi aplica, asigna categoria_sector a una de estas claves:\n"
            + "\n".join(lineas)
        )

    reglas_llm = [r for r in (matriz.reglas_no_alertar or []) if r.get("ejecutor") == "llm"]
    if reglas_llm:
        lineas = [f"- {r.get('clave')}: {r.get('descripcion')}" for r in reglas_llm]
        secciones.append(
            "## Reglas NO ALERTAR (semánticas)\n"
            "Si la publicación cae en alguna, devuelve su clave en regla_no_alertar:\n"
            + "\n".join(lineas)
        )

    if matriz.prompt_adicional:
        secciones.append(f"## Instrucciones adicionales\n{matriz.prompt_adicional}")

    campos = {
        "tipo": tipo_alerta,
        "titulo": alerta.get("titulo"),
        "contenido": alerta.get("contenido"),
        "autor": alerta.get("autor"),
        "url": alerta.get("url"),
        "red_social": alerta.get("red_social"),
        "fuente": alerta.get("fuente"),
        "ubicacion": alerta.get("ubicacion"),
        "reach": alerta.get("reach"),
        "engagement": alerta.get("engagement"),
        "fecha_publicacion": str(alerta.get("fecha_publicacion") or ""),
    }
    lineas = [f"{k}: {v}" for k, v in campos.items() if v not in (None, "")]
    secciones.append("## Publicación a evaluar\n" + "\n".join(lineas))

    return "\n\n".join(secciones)
