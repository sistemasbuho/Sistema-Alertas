# serializers.py
from rest_framework import serializers
from apps.base.models import TemplateConfig, TemplateCampoConfig
from django.apps import apps


class CampoPlantillaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateCampoConfig
        fields = ["id", "campo", "orden", "estilo"]


class PlantillaSerializer(serializers.ModelSerializer):
    campos = CampoPlantillaSerializer(many=True, required=False)

    class Meta:
        model = TemplateConfig
        fields = [
            "id",
            "nombre",
            "app_label",
            "model_name",
            "proyecto",
            "campos",
            "config_campos",  # 👈 nuevo campo agregado
        ]

    def create(self, validated_data):
        campos_data = validated_data.pop("campos", [])
        config_campos = validated_data.pop("config_campos", {})  # 👈 soporta config_campos
        plantilla = TemplateConfig.objects.create(**validated_data, config_campos=config_campos)

        for campo in campos_data:
            TemplateCampoConfig.objects.create(plantilla=plantilla, **campo)

        return plantilla

    def update(self, instance, validated_data):
        campos_data = validated_data.pop("campos", [])
        config_campos = validated_data.pop("config_campos", None)

        # Actualiza los atributos de la plantilla
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # 👇 si se envía config_campos se actualiza
        if config_campos is not None:
            instance.config_campos = config_campos

        instance.save()

        # Manejo de campos
        existing_ids = [c["id"] for c in campos_data if c.get("id")]
        TemplateCampoConfig.objects.filter(plantilla=instance).exclude(id__in=existing_ids).delete()

        for campo in campos_data:
            if campo.get("id"):
                # Actualizar campo existente
                campo_obj = TemplateCampoConfig.objects.get(id=campo["id"], plantilla=instance)
                campo_obj.campo = campo.get("campo", campo_obj.campo)
                campo_obj.orden = campo.get("orden", campo_obj.orden)
                campo_obj.estilo = campo.get("estilo", campo_obj.estilo)
                campo_obj.save()
            else:
                # Crear nuevo campo
                TemplateCampoConfig.objects.create(plantilla=instance, **campo)

        return instance

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        try:
            Model = apps.get_model(instance.app_label, instance.model_name)
        except LookupError:
            return rep  

        # todos los campos del modelo
        model_fields = [
            f.name for f in Model._meta.get_fields()
            if f.concrete and not f.auto_created
        ]

        # Config ya guardados
        config_campos = instance.config_campos or {}

        # Campos no configurados
        campos_no_config = []
        for idx, field_name in enumerate(model_fields, start=1):
            if field_name not in config_campos:
                campos_no_config.append({
                    "id": None,
                    "campo": field_name,
                    "orden": idx,
                    "estilo": {}
                })

        # En la respuesta:
        rep["campos"] = campos_no_config         # solo no configurados
        rep["config_campos"] = config_campos     # los ya configurados

        return rep


class CampoPlantillaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateCampoConfig
        fields = ["id", "campo", "orden", "estilo"]

    def create(self, validated_data):
        return TemplateCampoConfig.objects.create(**validated_data)