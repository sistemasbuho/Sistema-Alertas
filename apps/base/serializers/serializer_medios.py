from rest_framework import serializers
from apps.base.models import Articulo
from apps.base.models import DetalleEnvio, Articulo, Redes, TemplateConfig


class MediosSerializer(serializers.ModelSerializer):
    proyecto_nombre = serializers.SerializerMethodField()
    estado_revisado = serializers.SerializerMethodField()
    estado_enviado = serializers.SerializerMethodField()

    proyecto_keywords = serializers.SerializerMethodField()

    class Meta:
        model = Articulo
        fields = "__all__" 
        extra_fields = ['proyecto_nombre', 'estado_revisado', 'proyecto_keywords','estado_enviado']


    def get_proyecto_nombre(self, obj):
        return obj.proyecto.nombre if obj.proyecto else None

    def get_proyecto_keywords(self, obj):
        if obj.proyecto and obj.proyecto.keywords:
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
    
    def get_estado_enviado(self, obj):
        detalles = getattr(obj, "detalles_envio", None)

        if not detalles:
            return None  

        if all(getattr(d, "enviado", False) for d in detalles.all()):
            return "Enviado"

        if any(not getattr(d, "enviado", False) for d in detalles.all()):
            return "Pendiente"

        return None

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
