from rest_framework import serializers
from apps.proyectos.models import Proyecto

class ProyectoCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proyecto
        fields = [
            'id',
            'nombre',
            'proveedor',
            'codigo_acceso',
            'estado',
            'tipo_envio',
            'tipo_alerta',
            'formato_mensaje',
            'keywords',
            'created_at',
            'modified_at',
        ]
        read_only_fields = ['id', 'created_at', 'modified_at']

    def validate_nombre(self, value):
        """
        Valida que no exista otro proyecto con el mismo nombre
        """
        if Proyecto.objects.filter(nombre=value).exists():
            raise serializers.ValidationError("Ya existe un proyecto con este nombre.")
        return value