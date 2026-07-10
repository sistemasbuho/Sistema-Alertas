"""Decisión post-clasificación (D3/A4): auto-enviar, cola humana o descartar.

Toda la lógica es determinística; la salida del LLM entra como dato.
"""

from apps.base.models import DetalleEnvio
from apps.ia.models import EvaluacionIA, MatrizCliente

from . import reglas


def _campos_faltantes(matriz, tipo_alerta, alerta, salida):
    requeridos = (matriz.campos_requeridos_envio or {}).get(tipo_alerta, [])
    faltantes = []
    for campo in requeridos:
        if campo == "pais":
            if not salida.get("pais"):
                faltantes.append("pais")
            continue
        valor = alerta.get(campo)
        # reach en 0 "hace ruido" (C1): se trata como faltante-sospechoso
        if valor is None or valor == "" or (campo == "reach" and valor == 0):
            faltantes.append(campo)
    return faltantes


def _evaluar_nunca_autoenviar(matriz, salida, riesgo):
    """Reglas configurables por cliente que fuerzan cola humana aunque la
    confianza sea alta (vacías para L'Oréal: lo negativo ES el producto)."""
    aplicadas = []
    for regla in matriz.reglas_nunca_autoenviar or []:
        tipo = regla.get("tipo")
        if tipo == "tonalidad" and salida.get("tonalidad") == regla.get("valor"):
            aplicadas.append({"regla": "nunca_autoenviar", "tipo": tipo, "valor": regla.get("valor")})
        elif tipo == "riesgo" and riesgo == regla.get("valor"):
            aplicadas.append({"regla": "nunca_autoenviar", "tipo": tipo, "valor": regla.get("valor")})
    return aplicadas


def decidir(*, matriz, detalle, salida, tipo_alerta, alerta):
    """Tabla de decisión del gate. Devuelve un dict con:
    decision, decision_por, estado_pipeline, confianza, riesgo, riesgo_detalle,
    datos_faltantes, reglas_aplicadas.
    """
    umbrales = matriz.umbrales_para(tipo_alerta)
    reglas_aplicadas = []

    semaforo = None
    if matriz.incluir_semaforo:
        semaforo = reglas.calcular_semaforo(
            matriz.config_semaforo,
            red_social=alerta.get("red_social"),
            engagement=alerta.get("engagement"),
            reach=alerta.get("reach"),
            tonalidad=salida.get("tonalidad"),
        )
    riesgo = semaforo["riesgo"] if semaforo else None

    confianza = reglas.calcular_confianza(salida, requiere_pais=matriz.incluir_bandera)

    resultado = {
        "confianza": confianza,
        "riesgo": riesgo,
        "riesgo_detalle": semaforo["detalle"] if semaforo else None,
        "datos_faltantes": [],
        "reglas_aplicadas": reglas_aplicadas,
    }

    def _cerrar(decision, decision_por, estado):
        # En modo sombra la decisión queda registrada pero nada se auto-envía
        # ni auto-descarta: todo pasa por el humano (calibración A4).
        if matriz.modo == MatrizCliente.MODO_SOMBRA and estado != DetalleEnvio.PIPELINE_ENRIQUECIENDO:
            estado = DetalleEnvio.PIPELINE_COLA_EXCEPCIONES
        resultado.update(
            {"decision": decision, "decision_por": decision_por, "estado_pipeline": estado}
        )
        return resultado

    # 1) Regla semántica no-alertar detectada por el LLM
    if salida.get("regla_no_alertar"):
        reglas_aplicadas.append(
            {"regla": salida["regla_no_alertar"], "resultado": "descartada", "origen": "llm"}
        )
        return _cerrar(
            EvaluacionIA.DECISION_NO_ALERTAR_REGLA,
            EvaluacionIA.POR_REGLAS_POSTERIORES,
            DetalleEnvio.PIPELINE_DESCARTADA_IA,
        )

    # 2) Irrelevante
    if salida.get("relevante") is False:
        if (salida.get("relevancia_score") or 0) >= umbrales["descarte"]:
            return _cerrar(
                EvaluacionIA.DECISION_DESCARTAR,
                EvaluacionIA.POR_IA,
                DetalleEnvio.PIPELINE_DESCARTADA_IA,
            )
        return _cerrar(
            EvaluacionIA.DECISION_COLA,
            EvaluacionIA.POR_IA,
            DetalleEnvio.PIPELINE_COLA_EXCEPCIONES,
        )

    # 3) País fuera de la medición (re-check sobre lo detectado por el LLM)
    if matriz.paises and salida.get("pais") and salida["pais"] not in matriz.paises:
        reglas_aplicadas.append(
            {"regla": "pais_fuera_lista", "resultado": "cola", "pais": salida["pais"]}
        )
        return _cerrar(
            EvaluacionIA.DECISION_COLA,
            EvaluacionIA.POR_REGLAS_POSTERIORES,
            DetalleEnvio.PIPELINE_COLA_EXCEPCIONES,
        )

    # 4) Reglas nunca-autoenviar por cliente
    nunca = _evaluar_nunca_autoenviar(matriz, salida, riesgo)
    if nunca:
        reglas_aplicadas.extend(nunca)
        return _cerrar(
            EvaluacionIA.DECISION_COLA,
            EvaluacionIA.POR_REGLAS_POSTERIORES,
            DetalleEnvio.PIPELINE_COLA_EXCEPCIONES,
        )

    # 5) Confianza vs umbral
    if confianza < umbrales["auto_envio"]:
        return _cerrar(
            EvaluacionIA.DECISION_COLA,
            EvaluacionIA.POR_IA,
            DetalleEnvio.PIPELINE_COLA_EXCEPCIONES,
        )

    # 6) Alta confianza: ¿datos completos?
    faltantes = _campos_faltantes(matriz, tipo_alerta, alerta, salida)
    if faltantes:
        resultado["datos_faltantes"] = faltantes
        return _cerrar(
            EvaluacionIA.DECISION_AUTO_ENVIAR,
            EvaluacionIA.POR_IA,
            DetalleEnvio.PIPELINE_ENRIQUECIENDO,
        )

    return _cerrar(
        EvaluacionIA.DECISION_AUTO_ENVIAR,
        EvaluacionIA.POR_IA,
        DetalleEnvio.PIPELINE_AUTO_APROBADA,
    )
