from rest_framework import serializers
from apps.base.models import Redes


class RedesSerializer(serializers.ModelSerializer):
    proyecto_nombre = serializers.SerializerMethodField()
    estado_revisado = serializers.SerializerMethodField()
    proyecto_keywords = serializers.SerializerMethodField()


    class Meta:
        model = Redes
        fields = "__all__"
        extra_fields = ['proyecto_nombre', 'estado_revisado', 'proyecto_keywords']

    def get_proyecto_nombre(self, obj):
        return obj.proyecto.nombre if obj.proyecto else None


    def get_proyecto_keywords(self, obj):
        if obj.proyecto and obj.proyecto.keywords:
            # Devolver como lista (separadas por coma)
            return [kw.strip() for kw in obj.proyecto.keywords.split(",") if kw.strip()]
        return []  

    def get_estado_revisado(self, obj):
        detalles = getattr(obj, "detalles_envio", None)

        if not detalles:
            return None  

        if all(getattr(d, "revisado", False) for d in detalles.all()):
            return "Revisado"

        if any(not getattr(d, "revisado", False) for d in detalles.all()):
            return "Pendiente"

        return None

    def validate(self, data):
        """
        Validar que no se repita la URL en el mismo proyecto.
        """
        proyecto = data.get("proyecto", getattr(self.instance, "proyecto", None))
        url = data.get("url", getattr(self.instance, "url", None))

        if proyecto and url:
            qs = Redes.objects.filter(proyecto=proyecto, url=url)
            if self.instance:  # excluir el propio registro si es actualización
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise serializers.ValidationError(
                    {"url": "Ya existe un registro en Redes con esta URL en el mismo proyecto."}
                )

        return data