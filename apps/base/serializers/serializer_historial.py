
from rest_framework import serializers
from apps.base.models import *



class DetalleEnvioSerializer(serializers.ModelSerializer):
    usuario = serializers.CharField(source="usuario.username", read_only=True)
    proyecto = serializers.CharField(source="proyecto.nombre", read_only=True)
    red_social = serializers.CharField(source="red_social.red_social.nombre", read_only=True, default=None)

    tiempo_envio = serializers.SerializerMethodField()
    origen_envio = serializers.SerializerMethodField()
    evaluacion_ia_id = serializers.SerializerMethodField()

    class Meta:
        model = DetalleEnvio
        fields = [
            "id",
            "usuario",
            "proyecto",
            "mensaje",
            "created_at",
            "inicio_envio",
            "fin_envio",
            "tiempo_envio",
            "estado_enviado",
            "red_social",
            "estado_pipeline",
            "proveedor_envio",
            "origen_envio",
            "evaluacion_ia_id",
        ]

    def get_origen_envio(self, obj):
        if obj.estado_pipeline == DetalleEnvio.PIPELINE_MANUAL:
            return "humano"
        # auto_aprobada→enviada = IA; aprobada_humana→enviada = humano asistido
        ultima = obj.evaluaciones_ia.order_by("-created_at").first()
        if ultima is None:
            return "humano"
        return "humano" if ultima.revision_humana else "auto_ia"

    def get_evaluacion_ia_id(self, obj):
        ultima = obj.evaluaciones_ia.order_by("-created_at").first()
        return str(ultima.id) if ultima else None

    def get_tiempo_envio(self, obj):
        if obj.inicio_envio and obj.fin_envio:
            return (obj.fin_envio - obj.inicio_envio).total_seconds()
        return None