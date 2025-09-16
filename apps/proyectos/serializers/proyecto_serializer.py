from rest_framework import serializers
from apps.proyectos.models import Proyecto


class ProyectoCreateSerializer(serializers.ModelSerializer):
    grupo_nombre = serializers.CharField(read_only=True)  # 👉 ya no hace request al API en GET

    class Meta:
        model = Proyecto
        fields = [
            'id',
            'nombre',
            'proveedor',
            'codigo_acceso',
            'grupo_nombre',
            'estado',
            'tipo_envio',
            'tipo_alerta',
            'formato_mensaje',
            'keywords',
            'created_at',
            'modified_at',
        ]
        read_only_fields = ['id', 'created_at', 'modified_at', 'grupo_nombre']

    def validate_nombre(self, value):
        if Proyecto.objects.filter(nombre=value).exists():
            raise serializers.ValidationError("Ya existe un proyecto con este nombre.")
        return value


class ProyectoUpdateSerializer(serializers.ModelSerializer):
    grupo_nombre = serializers.CharField(read_only=True)  # 👉 ya no hace request al API en GET

    class Meta:
        model = Proyecto
        fields = [
            'id',
            'nombre',
            'proveedor',
            'codigo_acceso',
            'grupo_nombre',
            'estado',
            'tipo_envio',
            'tipo_alerta',
            'formato_mensaje',
            'keywords',
            'created_at',
            'modified_at',
        ]
        read_only_fields = ['id', 'created_at', 'modified_at', 'grupo_nombre']

    def validate_nombre(self, value):
        proyecto_actual = getattr(self, 'instance', None)
        if proyecto_actual:
            if Proyecto.objects.exclude(pk=proyecto_actual.pk).filter(nombre=value).exists():
                raise serializers.ValidationError("Ya existe un proyecto con este nombre.")
        else:
            if Proyecto.objects.filter(nombre=value).exists():
                raise serializers.ValidationError("Ya existe un proyecto con este nombre.")
        return value

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
