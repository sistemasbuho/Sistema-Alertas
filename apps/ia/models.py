from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from apps.base.models import BaseModel


class MatrizCliente(BaseModel):
    """Matriz de análisis del cliente digitalizada (Epic A2/A3/A4): la fuente
    de verdad de qué es relevante para cada proyecto, consumible por la IA."""

    MODO_SOMBRA = "sombra"
    MODO_ACTIVO = "activo"
    MODO_CHOICES = [
        (MODO_SOMBRA, "Sombra (clasifica pero todo va a cola humana)"),
        (MODO_ACTIVO, "Activo (auto-envía alta confianza)"),
    ]

    proyecto = models.OneToOneField(
        "proyectos.Proyecto",
        on_delete=models.CASCADE,
        related_name="matriz_ia",
        verbose_name="Proyecto",
    )
    activo = models.BooleanField(
        default=False,
        help_text="Switch maestro: si está apagado el proyecto usa el flujo legacy",
    )
    modo = models.CharField(max_length=10, choices=MODO_CHOICES, default=MODO_SOMBRA)

    descripcion_cliente = models.TextField(
        blank=True, help_text="Contexto libre del cliente para el prompt"
    )
    voceros = models.JSONField(
        default=list, blank=True, help_text='[{"nombre": "...", "notas": "..."}]'
    )
    marcas = models.JSONField(
        default=list, blank=True, help_text="Lista de marcas/menciones a vigilar"
    )
    menciones_criterio = models.TextField(
        blank=True, help_text="Criterio de relevancia en lenguaje natural"
    )
    paises = models.JSONField(
        default=list, blank=True, help_text="Países de la medición (ISO-3166-1 alpha-2)"
    )
    reglas_no_alertar = models.JSONField(
        default=list,
        blank=True,
        help_text='Reglas de exclusión; cada una con "ejecutor": "codigo" | "llm"',
    )
    criterios_sector = models.JSONField(
        default=list,
        blank=True,
        help_text='[{"clave": "belleza", "emoji": "💄", "descripcion": "..."}]',
    )
    esquema_tonalidad = models.JSONField(
        default=dict,
        blank=True,
        help_text='{"escala": [...], "definiciones": {...}, "foco": "negativo"}',
    )
    config_semaforo = models.JSONField(
        default=dict,
        blank=True,
        help_text="Config del semáforo; calculado SIEMPRE por código, nunca por LLM",
    )
    umbral_confianza = models.JSONField(
        default=dict,
        blank=True,
        help_text='{"redes": {"auto_envio": 0.85, "descarte": 0.90}, "medios": {...}}',
    )
    reglas_nunca_autoenviar = models.JSONField(
        default=list,
        blank=True,
        help_text="Condiciones que fuerzan cola humana aunque haya alta confianza",
    )
    incluir_bandera = models.BooleanField(default=False)
    incluir_semaforo = models.BooleanField(default=False)
    campos_requeridos_envio = models.JSONField(
        default=dict,
        blank=True,
        help_text='{"redes": ["pais", "reach"], "medios": ["pais", "titulo"]}',
    )
    prompt_adicional = models.TextField(blank=True)
    observaciones = models.TextField(
        blank=True, help_text="Notas operativas (frecuencia, etc.); no van al prompt"
    )

    history = HistoricalRecords(table_name="matriz_cliente_history")

    class Meta:
        verbose_name = "Matriz de cliente"
        verbose_name_plural = "Matrices de cliente"

    def __str__(self):
        return f"Matriz {self.proyecto.nombre} ({self.modo}{'/on' if self.activo else '/off'})"

    def umbrales_para(self, tipo_alerta):
        base = {"auto_envio": 0.85, "descarte": 0.90}
        return {**base, **self.umbral_confianza.get(tipo_alerta, {})}


class EvaluacionIA(BaseModel):
    """Registro auditable de cada decisión de la IA sobre una alerta (D5),
    incluyendo la corrección humana cuando la hay (D4)."""

    ESTADO_PENDIENTE = "pendiente"
    ESTADO_PROCESANDO = "procesando"
    ESTADO_COMPLETADA = "completada"
    ESTADO_TIMEOUT = "timeout"
    ESTADO_ERROR = "error"
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_PROCESANDO, "Procesando"),
        (ESTADO_COMPLETADA, "Completada"),
        (ESTADO_TIMEOUT, "Timeout"),
        (ESTADO_ERROR, "Error"),
    ]

    DECISION_AUTO_ENVIAR = "auto_enviar"
    DECISION_COLA = "cola_excepciones"
    DECISION_DESCARTAR = "descartar"
    DECISION_NO_ALERTAR_REGLA = "no_alertar_regla"
    DECISION_CHOICES = [
        (DECISION_AUTO_ENVIAR, "Auto enviar"),
        (DECISION_COLA, "Cola de excepciones"),
        (DECISION_DESCARTAR, "Descartar"),
        (DECISION_NO_ALERTAR_REGLA, "No alertar (regla dura)"),
    ]

    POR_REGLAS_PREVIAS = "reglas_previas"
    POR_IA = "ia"
    POR_REGLAS_POSTERIORES = "reglas_posteriores"
    POR_TIMEOUT = "timeout_fallback"
    POR_ERROR = "error_fallback"
    DECISION_POR_CHOICES = [
        (POR_REGLAS_PREVIAS, "Reglas previas"),
        (POR_IA, "IA"),
        (POR_REGLAS_POSTERIORES, "Reglas posteriores"),
        (POR_TIMEOUT, "Fallback por timeout"),
        (POR_ERROR, "Fallback por error"),
    ]

    REVISION_CONFIRMADA = "confirmada"
    REVISION_CORREGIDA = "corregida"
    REVISION_RECHAZADA = "rechazada"
    REVISION_CHOICES = [
        (REVISION_CONFIRMADA, "Confirmada"),
        (REVISION_CORREGIDA, "Corregida"),
        (REVISION_RECHAZADA, "Rechazada"),
    ]

    detalle_envio = models.ForeignKey(
        "base.DetalleEnvio",
        on_delete=models.CASCADE,
        related_name="evaluaciones_ia",
    )
    proyecto = models.ForeignKey(
        "proyectos.Proyecto",
        on_delete=models.CASCADE,
        related_name="evaluaciones_ia",
    )
    tipo_alerta = models.CharField(max_length=10)  # redes | medios
    estado = models.CharField(
        max_length=15, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE
    )

    # Salida de la IA
    relevante = models.BooleanField(null=True, blank=True)
    relevancia_score = models.FloatField(null=True, blank=True)
    tonalidad = models.CharField(max_length=15, null=True, blank=True)
    tonalidad_score = models.FloatField(null=True, blank=True)
    categoria_sector = models.CharField(max_length=50, null=True, blank=True)
    pais_detectado = models.CharField(max_length=2, null=True, blank=True)
    pais_score = models.FloatField(null=True, blank=True)
    confianza_global = models.FloatField(null=True, blank=True)
    marca_detectada = models.CharField(max_length=100, null=True, blank=True)

    # Decisión + trazabilidad (D5)
    decision = models.CharField(
        max_length=20, choices=DECISION_CHOICES, null=True, blank=True
    )
    decision_por = models.CharField(
        max_length=20, choices=DECISION_POR_CHOICES, null=True, blank=True
    )
    razones = models.JSONField(default=list, blank=True)
    reglas_aplicadas = models.JSONField(default=list, blank=True)
    riesgo = models.CharField(max_length=10, null=True, blank=True)  # bajo|medio|alto
    riesgo_detalle = models.JSONField(null=True, blank=True)
    datos_faltantes = models.JSONField(default=list, blank=True)
    datos_completados = models.JSONField(default=list, blank=True)

    # Metadatos del modelo/operación
    modelo = models.CharField(max_length=60, null=True, blank=True)
    version_prompt = models.CharField(max_length=20, null=True, blank=True)
    latencia_ms = models.IntegerField(null=True, blank=True)
    tokens_entrada = models.IntegerField(null=True, blank=True)
    tokens_salida = models.IntegerField(null=True, blank=True)
    respuesta_cruda = models.JSONField(null=True, blank=True)
    snapshot_matriz = models.JSONField(null=True, blank=True)

    # Loop de feedback humano (D4 → ajuste de umbrales A4)
    revision_humana = models.CharField(
        max_length=15, choices=REVISION_CHOICES, null=True, blank=True
    )
    correccion = models.JSONField(null=True, blank=True)
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revisiones_ia",
    )
    revisado_en = models.DateTimeField(null=True, blank=True)
    comentario_revision = models.TextField(blank=True)

    history = HistoricalRecords(table_name="evaluacion_ia_history")

    class Meta:
        verbose_name = "Evaluación IA"
        verbose_name_plural = "Evaluaciones IA"
        indexes = [
            models.Index(fields=["proyecto", "decision", "created_at"]),
            models.Index(fields=["estado"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"EvaluacionIA {self.id} [{self.decision or self.estado}]"


class EnriquecimientoLog(BaseModel):
    """Auditoría del completado de datos faltantes (Epic C)."""

    detalle_envio = models.ForeignKey(
        "base.DetalleEnvio",
        on_delete=models.CASCADE,
        related_name="enriquecimientos",
    )
    campo = models.CharField(max_length=50)
    valor_anterior = models.TextField(null=True, blank=True)
    valor_nuevo = models.TextField(null=True, blank=True)
    fuente = models.CharField(
        max_length=20
    )  # proveedor | scrapegraph | similarweb | brightdata | heuristica
    exito = models.BooleanField(default=False)
    error = models.TextField(null=True, blank=True)
    latencia_ms = models.IntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Log de enriquecimiento"
        verbose_name_plural = "Logs de enriquecimiento"
