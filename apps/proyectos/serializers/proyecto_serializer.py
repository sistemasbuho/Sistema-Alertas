from rest_framework import serializers
from apps.proyectos.models import Proyecto
from django.conf import settings
import requests
import os

WHATSAPP_ACCESS_KEY = os.getenv("WHAPI_TOKEN")



class ProyectoCreateSerializer(serializers.ModelSerializer):
    grupo_nombre = serializers.SerializerMethodField(read_only=True)  # 👈 Campo calculado

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
        """
        Valida que no exista otro proyecto con el mismo nombre
        """
        if Proyecto.objects.filter(nombre=value).exists():
            raise serializers.ValidationError("Ya existe un proyecto con este nombre.")
        return value

    def get_grupo_nombre(self, obj):
        """
        Obtiene el nombre del grupo desde la API de WhatsApp
        usando el codigo_acceso (ID del grupo).
        """
        if not obj.codigo_acceso:
            return None

        url_grupos = "https://gate.whapi.cloud/groups"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_ACCESS_KEY}",
            "Content-Type": "application/json"
        }
        response = requests.get(url_grupos, headers=headers)
        if response.status_code == 200:
            data = response.json()
            grupo = next((g for g in data['groups'] if g['id'] == obj.codigo_acceso), None)
            return grupo['name'] if grupo else None

        return None


class ProyectoUpdateSerializer(serializers.ModelSerializer):
    grupo_nombre = serializers.SerializerMethodField(read_only=True)  # 👈 Campo calculado

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
        """
        Valida que no exista otro proyecto con el mismo nombre,
        pero permite mantener el nombre actual si no cambia.
        """
        proyecto_actual = getattr(self, 'instance', None)
        if proyecto_actual:
            if Proyecto.objects.exclude(pk=proyecto_actual.pk).filter(nombre=value).exists():
                raise serializers.ValidationError("Ya existe un proyecto con este nombre.")
        else:
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

    def get_grupo_nombre(self, obj):
        """
        Obtiene el nombre del grupo desde la API de WhatsApp
        usando el codigo_acceso (ID del grupo).
        """
        if not obj.codigo_acceso:
            return None

        url_grupos = "https://gate.whapi.cloud/groups"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_ACCESS_KEY}",
            "Content-Type": "application/json"
        }
        response = requests.get(url_grupos, headers=headers)
        if response.status_code == 200:
            data = response.json()
            grupo = next((g for g in data['groups'] if g['id'] == obj.codigo_acceso), None)
            return grupo['name'] if grupo else None

        return None