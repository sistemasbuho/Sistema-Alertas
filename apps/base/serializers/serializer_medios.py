from rest_framework import serializers
from apps.base.models import Articulo

class MediosSerializer(serializers.ModelSerializer):
    proyecto_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Articulo
        fields = "__all__"  # incluye todos los campos + proyecto_nombre

    def get_proyecto_nombre(self, obj):
        return obj.proyecto.nombre if obj.proyecto else None

    def validate(self, data):
        """
        Validar que no se repita la URL en el mismo proyecto.
        """
        # Si es un update, obtenemos valores existentes
        proyecto = data.get("proyecto", getattr(self.instance, "proyecto", None))
        url = data.get("url", getattr(self.instance, "url", None))

        if proyecto and url:
            qs = Articulo.objects.filter(proyecto=proyecto, url=url)
            if self.instance:  # si es actualización, excluir el propio registro
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise serializers.ValidationError(
                    {"url": "Ya existe un artículo con esta URL en el mismo proyecto."}
                )

        return data
