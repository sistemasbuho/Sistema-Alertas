from rest_framework import serializers

from apps.ia.models import EvaluacionIA


class EvaluacionIAResumenSerializer(serializers.ModelSerializer):
    """Resumen embebible en listados de alertas / cola de excepciones."""

    estado_ia = serializers.SerializerMethodField()

    class Meta:
        model = EvaluacionIA
        fields = [
            "id",
            "estado_ia",
            "estado",
            "decision",
            "decision_por",
            "relevante",
            "relevancia_score",
            "tonalidad",
            "tonalidad_score",
            "categoria_sector",
            "pais_detectado",
            "confianza_global",
            "riesgo",
            "razones",
            "datos_faltantes",
            "datos_completados",
            "revision_humana",
            "created_at",
        ]

    def get_estado_ia(self, obj):
        return obj.detalle_envio.estado_pipeline if obj.detalle_envio_id else None


class EvaluacionIADetalleSerializer(EvaluacionIAResumenSerializer):
    """Detalle completo para auditoría D5 ('¿por qué se envió?')."""

    revisado_por = serializers.SerializerMethodField()

    class Meta(EvaluacionIAResumenSerializer.Meta):
        fields = EvaluacionIAResumenSerializer.Meta.fields + [
            "detalle_envio",
            "proyecto",
            "tipo_alerta",
            "pais_score",
            "marca_detectada",
            "riesgo_detalle",
            "reglas_aplicadas",
            "modelo",
            "version_prompt",
            "latencia_ms",
            "tokens_entrada",
            "tokens_salida",
            "respuesta_cruda",
            "snapshot_matriz",
            "correccion",
            "revisado_por",
            "revisado_en",
            "comentario_revision",
        ]

    def get_revisado_por(self, obj):
        return obj.revisado_por.username if obj.revisado_por else None
