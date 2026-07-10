"""Cliente Vertex AI (Gemini) vía SDK unificado google-genai.

Autenticación: GOOGLE_APPLICATION_CREDENTIALS (service account) +
VERTEX_PROJECT_ID / VERTEX_LOCATION. Salida estructurada nativa con Pydantic.
"""

import time
from dataclasses import dataclass
from typing import Optional

from django.conf import settings

_cliente = None


@dataclass
class MetadatosLLM:
    modelo: str
    latencia_ms: int
    tokens_entrada: Optional[int] = None
    tokens_salida: Optional[int] = None


def _get_cliente():
    global _cliente
    if _cliente is None:
        from google import genai

        _cliente = genai.Client(
            vertexai=True,
            project=settings.VERTEX_PROJECT_ID,
            location=settings.VERTEX_LOCATION,
        )
    return _cliente


def clasificar(prompt, schema):
    """Ejecuta la clasificación y devuelve (dict_validado, MetadatosLLM).

    Lanza excepción en fallo de red/API/parseo: el caller decide el fallback
    (B3: cola humana).
    """
    cliente = _get_cliente()
    modelo = settings.GEMINI_MODEL

    inicio = time.monotonic()
    respuesta = cliente.models.generate_content(
        model=modelo,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": schema,
            "temperature": 0.1,
        },
    )
    latencia_ms = int((time.monotonic() - inicio) * 1000)

    parsed = respuesta.parsed
    datos = parsed.model_dump() if hasattr(parsed, "model_dump") else dict(parsed)

    uso = getattr(respuesta, "usage_metadata", None)
    metadatos = MetadatosLLM(
        modelo=modelo,
        latencia_ms=latencia_ms,
        tokens_entrada=getattr(uso, "prompt_token_count", None),
        tokens_salida=getattr(uso, "candidates_token_count", None),
    )
    return datos, metadatos
