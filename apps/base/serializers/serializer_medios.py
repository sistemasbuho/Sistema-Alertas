from rest_framework import serializers
from apps.base.models import Articulo

class MediosSerializer(serializers.ModelSerializer):
    proyecto_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Articulo
        fields = '__all__'  # devuelve todos los campos del modelo
        # y además agregamos proyecto_nombre

    def get_proyecto_nombre(self, obj):
        return obj.proyecto.nombre if obj.proyecto else None
