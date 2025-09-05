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
        fields = ["id", "nombre", "app_label", "model_name", "proyecto", "campos"]

    def create(self, validated_data):
        campos_data = validated_data.pop("campos", [])
        plantilla = TemplateConfig.objects.create(**validated_data)

        for campo in campos_data:
            TemplateCampoConfig.objects.create(plantilla=plantilla, **campo)

        return plantilla

    def update(self, instance, validated_data):
        campos_data = validated_data.pop("campos", [])

        # Actualiza los atributos de la plantilla
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
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
        """
        Muestra campos guardados con estilo,
        y además los campos del modelo que no tienen configuración aún.
        """
        rep = super().to_representation(instance)

        try:
            Model = apps.get_model(instance.app_label, instance.model_name)
        except LookupError:
            return rep  

        # Todos los campos del modelo
        model_fields = [
            f.name for f in Model._meta.get_fields()
            if f.concrete and not f.auto_created
        ]

        # Campos ya guardados
        campos_guardados = {c["campo"]: c for c in CampoPlantillaSerializer(instance.campos.all(), many=True).data}

        # Mezclamos: primero los guardados, luego los que faltan
        campos_finales = []
        orden = 1

        for field_name in model_fields:
            if field_name in campos_guardados:
                campo = campos_guardados[field_name]
            else:
                campo = {
                    "id": None,
                    "campo": field_name,
                    "orden": orden,
                    "estilo": {}
                }
            campo["orden"] = orden
            campos_finales.append(campo)
            orden += 1

        rep["campos"] = campos_finales
        return rep



class CampoPlantillaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateCampoConfig
        fields = ["id", "campo", "orden", "estilo"]

    def create(self, validated_data):
        return TemplateCampoConfig.objects.create(**validated_data)