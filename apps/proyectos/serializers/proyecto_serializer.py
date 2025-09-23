from rest_framework import serializers
from django.db import transaction

from apps.proyectos.models import Proyecto
from apps.base.models import TemplateConfig, Articulo, Redes
from apps.base.utils import generar_plantilla_desde_modelo


class ProyectoCreateSerializer(serializers.ModelSerializer):
    # grupo_nombre = serializers.CharField(read_only=True)

    class Meta:
        model = Proyecto
        fields = [
            'id',
            'nombre',
            'proveedor',
            'codigo_acceso',
            'nombre_grupo',
            'estado',
            'tipo_envio',
            'tipo_alerta',
            'formato_mensaje',
            'keywords',
            'criterios_aceptacion',
            'created_at',
            'modified_at',
        ]
        read_only_fields = ['id', 'created_at', 'modified_at']

    def validate_nombre(self, value):
        if Proyecto.objects.filter(nombre=value).exists():
            raise serializers.ValidationError("Ya existe un proyecto con este nombre.")
        return value

    def create(self, validated_data):
        with transaction.atomic():
            proyecto = Proyecto.objects.create(**validated_data)
            self._crear_plantilla_por_defecto(proyecto)
        return proyecto

    def _crear_plantilla_por_defecto(self, proyecto: Proyecto) -> None:
        mapping = {
            "medios": (Articulo, "Plantilla Medios"),
            "redes": (Redes, "Plantilla Redes"),
        }

        modelo_config = mapping.get(proyecto.tipo_alerta)
        if not modelo_config:
            return

        model, nombre = modelo_config
        config_campos = generar_plantilla_desde_modelo(
            model,
            campos_excluir={
                "id",
                "created_at",
                "modified_at",
                "created_by",
                "modified_by",
                "proyecto",
            },
        )

        TemplateConfig.objects.get_or_create(
            proyecto=proyecto,
            app_label=model._meta.app_label,
            model_name=model._meta.model_name,
            defaults={
                "nombre": nombre,
                "config_campos": config_campos,
            },
        )


class ProyectoUpdateSerializer(serializers.ModelSerializer):
    # grupo_nombre = serializers.CharField(read_only=True) 

    class Meta:
        model = Proyecto
        fields = [
            'id',
            'nombre',
            'proveedor',
            'codigo_acceso',
            'nombre_grupo',
            'estado',
            'tipo_envio',
            'tipo_alerta',
            'formato_mensaje',
            'keywords',
            'criterios_aceptacion',
            'created_at',
            'modified_at',
        ]
        read_only_fields = ['id', 'created_at', 'modified_at']

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
