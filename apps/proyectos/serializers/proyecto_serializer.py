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

class ProyectoUpdateSerializer(serializers.ModelSerializer):
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
        Valida que no exista otro proyecto con el mismo nombre,
        pero permite mantener el nombre actual si no cambia.
        """
        proyecto_actual = getattr(self, 'instance', None)
        if proyecto_actual:
            # Solo buscar duplicados entre otros proyectos
            if Proyecto.objects.exclude(pk=proyecto_actual.pk).filter(nombre=value).exists():
                raise serializers.ValidationError("Ya existe un proyecto con este nombre.")
        else:
            # En caso de que se use sin instancia (teórico)
            if Proyecto.objects.filter(nombre=value).exists():
                raise serializers.ValidationError("Ya existe un proyecto con este nombre.")
        return value

    def update(self, instance, validated_data):
        """
        Actualiza todos los campos del proyecto.
        """
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance