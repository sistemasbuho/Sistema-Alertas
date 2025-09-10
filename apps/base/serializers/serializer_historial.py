
from rest_framework import serializers
from apps.base.models import *



class DetalleEnvioSerializer(serializers.ModelSerializer):
    usuario = serializers.CharField(source="usuario.username", read_only=True)
    proyecto = serializers.CharField(source="proyecto.nombre", read_only=True)
    red_social = serializers.CharField(source="red_social.red_social.nombre", read_only=True, default=None)

    tiempo_envio = serializers.SerializerMethodField()

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
        ]

    def get_tiempo_envio(self, obj):
        if obj.inicio_envio and obj.fin_envio:
            return (obj.fin_envio - obj.inicio_envio).total_seconds()
        return None