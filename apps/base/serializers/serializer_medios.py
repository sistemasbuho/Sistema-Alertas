from rest_framework import serializers
from apps.base.models import Articulo

class MediosSerializer(serializers.ModelSerializer):
    proyecto_nombre = serializers.SerializerMethodField()
    mensaje_formateado = serializers.SerializerMethodField()  # 👈 nuevo campo

    class Meta:
        model = Articulo
        fields = "__all__"  # incluye todos los campos del modelo
        extra_fields = ["proyecto_nombre", "mensaje_formateado"]

    def get_proyecto_nombre(self, obj):
        return obj.proyecto.nombre if obj.proyecto else None

    def get_mensaje_formateado(self, obj):
        """
        Genera un mensaje formateado aplicando una plantilla de estilos.
        La plantilla se pasa en el contexto o usa un valor por defecto.
        """
        plantilla = self.context.get("plantilla", {
            "titulo": {"orden": 1, "estilo": {"negrita": True}},
            "contenido": {"orden": 2, "estilo": {"inclinado": True}},
            "mensaje": {"orden": 3, "estilo": {}},
        })

        alerta = {
            "titulo": getattr(obj, "titulo", None),
            "contenido": getattr(obj, "contenido", None),
            "mensaje": getattr(obj, "mensaje", None),
        }

        from apps.utils import formatear_mensaje  # 👈 importa tu función
        return formatear_mensaje(alerta, plantilla)

    def validate(self, data):
        """
        Validar que no se repita la URL en el mismo proyecto.
        """
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
