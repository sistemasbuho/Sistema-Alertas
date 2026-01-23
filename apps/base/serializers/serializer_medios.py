from rest_framework import serializers
from apps.base.models import Articulo
from apps.base.models import DetalleEnvio, Articulo, Redes, TemplateConfig
from apps.base.api.utils import limpiar_texto
from django.utils import timezone
from datetime import datetime
import pytz


class MediosSerializer(serializers.ModelSerializer):
    proyecto_nombre = serializers.SerializerMethodField()
    estado_revisado = serializers.SerializerMethodField()
    estado_enviado = serializers.SerializerMethodField()

    proyecto_keywords = serializers.SerializerMethodField()
    fecha_publicacion = serializers.DateTimeField(required=False, allow_null=True)

    class Meta:
        model = Articulo
        fields = "__all__"
        read_only_fields = ['created_at', 'modified_at', 'created_by', 'modified_by']


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

        if all(getattr(d, "estado_revisado", False) for d in detalles.all()):
            return "Revisado"

        if any(not getattr(d, "estado_revisado", False) for d in detalles.all()):
            return "Pendiente"

        return None
    
    def get_estado_enviado(self, obj):
        detalles = getattr(obj, "detalles_envio", None)

        if not detalles:
            return None  

        if all(getattr(d, "estado_enviado", False) for d in detalles.all()):
            return "Enviado"

        if any(not getattr(d, "estado_enviado", False) for d in detalles.all()):
            return "Pendiente"

        return None

    def to_internal_value(self, data):
        """
        Procesar la fecha_publicacion antes de la validación para mantener el timezone correcto.
        También aplica limpieza de texto a los campos de texto.
        """
        internal_data = super().to_internal_value(data)

        # Si hay fecha_publicacion en los datos entrantes
        if 'fecha_publicacion' in internal_data and internal_data['fecha_publicacion']:
            fecha = internal_data['fecha_publicacion']
            # Si la fecha es naive (sin timezone), asumimos que ya está en UTC
            if timezone.is_naive(fecha):
                internal_data['fecha_publicacion'] = timezone.make_aware(fecha, pytz.UTC)

        # Limpiar campos de texto
        campos_texto = ['titulo', 'contenido', 'autor', 'fuente']
        for campo in campos_texto:
            if campo in internal_data:
                internal_data[campo] = limpiar_texto(internal_data[campo])

        return internal_data

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
