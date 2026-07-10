from rest_framework import serializers

from apps.ia.models import MatrizCliente


class MatrizClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = MatrizCliente
        fields = [
            "id",
            "proyecto",
            "activo",
            "modo",
            "descripcion_cliente",
            "voceros",
            "marcas",
            "menciones_criterio",
            "paises",
            "reglas_no_alertar",
            "criterios_sector",
            "esquema_tonalidad",
            "config_semaforo",
            "umbral_confianza",
            "reglas_nunca_autoenviar",
            "incluir_bandera",
            "incluir_semaforo",
            "campos_requeridos_envio",
            "prompt_adicional",
            "observaciones",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "proyecto", "created_at", "modified_at"]
