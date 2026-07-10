"""Orquestación de la clasificación de una alerta:
pre-reglas (código) → LLM (Gemini) → post-reglas + gate (código).
"""

import logging

from django.utils import timezone

from apps.base.models import DetalleEnvio
from apps.ia.models import EvaluacionIA

from . import reglas, vertex
from .gate import decidir
from .prompts import PROMPT_VERSION, SalidaClasificacion, construir_prompt_clasificacion

logger = logging.getLogger(__name__)


def _alerta_dict(detalle):
    """Payload plano de la alerta desde el Articulo/Redes vinculado."""
    objeto = detalle.red_social or detalle.medio
    if objeto is None:
        return None, None

    tipo_alerta = "redes" if detalle.red_social_id else "medios"
    alerta = {
        "titulo": getattr(objeto, "titulo", None),
        "contenido": objeto.contenido,
        "url": objeto.url,
        "autor": objeto.autor,
        "fuente": getattr(objeto, "fuente", None),
        "ubicacion": objeto.ubicacion,
        "reach": objeto.reach,
        "engagement": objeto.engagement,
        "fecha_publicacion": objeto.fecha_publicacion,
        "red_social": (
            objeto.red_social.nombre if tipo_alerta == "redes" and objeto.red_social else None
        ),
    }
    return alerta, tipo_alerta


def _snapshot_matriz(matriz):
    return {
        "modo": matriz.modo,
        "marcas": matriz.marcas,
        "paises": matriz.paises,
        "umbral_confianza": matriz.umbral_confianza,
        "reglas_no_alertar": matriz.reglas_no_alertar,
        "reglas_nunca_autoenviar": matriz.reglas_nunca_autoenviar,
        "config_semaforo": matriz.config_semaforo,
        "campos_requeridos_envio": matriz.campos_requeridos_envio,
    }


def clasificar_detalle(detalle, matriz):
    """Clasifica una alerta y aplica la decisión del gate.

    Devuelve la EvaluacionIA creada. Las excepciones del LLM se propagan
    (el caller aplica el fallback a cola humana, B3).
    """
    alerta, tipo_alerta = _alerta_dict(detalle)
    if alerta is None:
        logger.warning("DetalleEnvio %s sin alerta vinculada", detalle.id)
        return None

    evaluacion = EvaluacionIA(
        detalle_envio=detalle,
        proyecto=detalle.proyecto,
        tipo_alerta=tipo_alerta,
        estado=EvaluacionIA.ESTADO_PROCESANDO,
        snapshot_matriz=_snapshot_matriz(matriz),
        version_prompt=PROMPT_VERSION,
    )

    # 1) Reglas previas en código: descartan sin gastar LLM
    previas = reglas.evaluar_reglas_previas(
        matriz.reglas_no_alertar, alerta, paises=matriz.paises
    )
    if previas:
        evaluacion.estado = EvaluacionIA.ESTADO_COMPLETADA
        evaluacion.decision = EvaluacionIA.DECISION_NO_ALERTAR_REGLA
        evaluacion.decision_por = EvaluacionIA.POR_REGLAS_PREVIAS
        evaluacion.reglas_aplicadas = previas
        evaluacion.razones = [
            f"Regla dura: {r['regla']}" for r in previas
        ]
        evaluacion.save()
        # En modo sombra también se registra, pero no se descarta de verdad
        if matriz.modo == matriz.MODO_SOMBRA:
            detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_COLA_EXCEPCIONES)
        else:
            detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_DESCARTADA_IA)
        return evaluacion

    # 2) LLM
    prompt = construir_prompt_clasificacion(matriz, alerta, tipo_alerta)
    salida, metadatos = vertex.clasificar(prompt, SalidaClasificacion)

    evaluacion.relevante = salida.get("relevante")
    evaluacion.relevancia_score = salida.get("relevancia_score")
    evaluacion.tonalidad = salida.get("tonalidad")
    evaluacion.tonalidad_score = salida.get("tonalidad_score")
    evaluacion.categoria_sector = salida.get("categoria_sector")
    evaluacion.pais_detectado = salida.get("pais")
    evaluacion.pais_score = salida.get("pais_score")
    evaluacion.marca_detectada = salida.get("marca_detectada")
    evaluacion.razones = salida.get("razones") or []
    evaluacion.respuesta_cruda = salida
    evaluacion.modelo = metadatos.modelo
    evaluacion.latencia_ms = metadatos.latencia_ms
    evaluacion.tokens_entrada = metadatos.tokens_entrada
    evaluacion.tokens_salida = metadatos.tokens_salida

    # 3) Gate determinístico
    decision = decidir(
        matriz=matriz,
        detalle=detalle,
        salida=salida,
        tipo_alerta=tipo_alerta,
        alerta=alerta,
    )
    evaluacion.decision = decision["decision"]
    evaluacion.decision_por = decision["decision_por"]
    evaluacion.confianza_global = decision["confianza"]
    evaluacion.riesgo = decision["riesgo"]
    evaluacion.riesgo_detalle = decision["riesgo_detalle"]
    evaluacion.datos_faltantes = decision["datos_faltantes"]
    evaluacion.reglas_aplicadas = (evaluacion.reglas_aplicadas or []) + decision["reglas_aplicadas"]
    evaluacion.estado = EvaluacionIA.ESTADO_COMPLETADA
    evaluacion.save()

    detalle.aplicar_estado_pipeline(decision["estado_pipeline"])
    return evaluacion


def registrar_fallback(detalle, matriz, *, motivo, decision_por):
    """B3: la IA no respondió a tiempo o falló → cola humana, nunca retraso."""
    EvaluacionIA.objects.create(
        detalle_envio=detalle,
        proyecto=detalle.proyecto,
        tipo_alerta="redes" if detalle.red_social_id else "medios",
        estado=(
            EvaluacionIA.ESTADO_TIMEOUT
            if decision_por == EvaluacionIA.POR_TIMEOUT
            else EvaluacionIA.ESTADO_ERROR
        ),
        decision=EvaluacionIA.DECISION_COLA,
        decision_por=decision_por,
        razones=[motivo],
        snapshot_matriz=_snapshot_matriz(matriz) if matriz else None,
        version_prompt=PROMPT_VERSION,
    )
    detalle.aplicar_estado_pipeline(DetalleEnvio.PIPELINE_COLA_EXCEPCIONES)
