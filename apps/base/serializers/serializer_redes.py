from rest_framework import serializers
from apps.base.models import Redes
from apps.base.api.utils import limpiar_texto
from django.utils import timezone
from datetime import datetime
import pytz


def obtener_contenido_twitter(texto):
    """
    Devuelve el texto hasta QT/Repost (incluyendo la palabra).
    """
    qt_index = texto.find("QT")
    repost_index = texto.find("Repost")
    indices = [i for i in [qt_index, repost_index] if i != -1]
    if indices:
        corte = min(indices)
        # Agregamos la longitud de la palabra encontrada
        if corte == qt_index:
            corte += len("QT")
        elif corte == repost_index:
            corte += len("Repost")
        return texto[:corte].strip()
    return texto.strip()


class DetalleEnvioEmbeddedSerializer(serializers.Serializer):
    """Serializer optimizado para detalles de envío embebidos"""
    id = serializers.UUIDField()
    mensaje = serializers.SerializerMethodField()
    estado_enviado = serializers.BooleanField()
    estado_revisado = serializers.BooleanField()
    inicio_envio = serializers.DateTimeField()
    fin_envio = serializers.DateTimeField()
    qt = serializers.SerializerMethodField()

    def get_mensaje(self, obj):
        mensaje = obj.mensaje or ""
        red_social = self.context.get('red_social')

        if red_social and red_social.nombre and red_social.nombre.lower() == "twitter":
            return obtener_contenido_twitter(mensaje)
        return mensaje

    def get_qt(self, obj):
        mensaje = obj.mensaje or ""
        red_social = self.context.get('red_social')

        if red_social and red_social.nombre and red_social.nombre.lower() == "twitter":
            return "Sí" if "QT" in mensaje or "Repost" in mensaje else "No"
        return "No"


class RedesSerializer(serializers.ModelSerializer):
    proyecto_nombre = serializers.SerializerMethodField()
    estado_revisado = serializers.SerializerMethodField()
    estado_enviado = serializers.SerializerMethodField()
    proyecto_keywords = serializers.SerializerMethodField()
    fecha_publicacion = serializers.DateTimeField(required=False, allow_null=True)
    detalles_envio = serializers.SerializerMethodField()


    class Meta:
        model = Redes
        fields = "__all__"
        read_only_fields = ['created_at', 'modified_at', 'created_by', 'modified_by']

    def get_proyecto_nombre(self, obj):
        return obj.proyecto.nombre if obj.proyecto else None


    def get_proyecto_keywords(self, obj):
        if obj.proyecto and obj.proyecto.keywords:
            # Devolver como lista (separadas por coma)
            return [kw.strip() for kw in obj.proyecto.keywords.split(",") if kw.strip()]
        return []

    def get_detalles_envio(self, obj):
        """Serializa detalles de envío usando el prefetch_related optimizado"""
        # Usar all() para aprovechar el prefetch_related, no genera query adicional
        detalles = obj.detalles_envio.all()
        return DetalleEnvioEmbeddedSerializer(
            detalles,
            many=True,
            context={'red_social': obj.red_social}
        ).data

    def get_estado_revisado(self, obj):
        """Usa el prefetch_related para evitar queries adicionales"""
        detalles = obj.detalles_envio.all()  # No genera query adicional gracias a prefetch_related

        if not detalles:
            return None

        # Convertir a lista para evaluar una sola vez
        detalles_list = list(detalles)

        if not detalles_list:
            return None

        if all(d.estado_revisado for d in detalles_list):
            return "Revisado"

        if any(not d.estado_revisado for d in detalles_list):
            return "Pendiente"

        return None

    def get_estado_enviado(self, obj):
        """Usa el prefetch_related para evitar queries adicionales"""
        detalles = obj.detalles_envio.all()  # No genera query adicional gracias a prefetch_related

        if not detalles:
            return None

        # Convertir a lista para evaluar una sola vez
        detalles_list = list(detalles)

        if not detalles_list:
            return None

        if all(d.estado_enviado for d in detalles_list):
            return "Enviado"

        if any(not d.estado_enviado for d in detalles_list):
            return "Pendiente"

        return None

    def to_internal_value(self, data):
        """
        Procesar la fecha_publicacion antes de la validación para mantener el timezone correcto.
        """
        internal_data = super().to_internal_value(data)

        # Si hay fecha_publicacion en los datos entrantes
        if 'fecha_publicacion' in internal_data and internal_data['fecha_publicacion']:
            fecha = internal_data['fecha_publicacion']
            # Si la fecha es naive (sin timezone), asumimos que ya está en UTC
            if timezone.is_naive(fecha):
                internal_data['fecha_publicacion'] = timezone.make_aware(fecha, pytz.UTC)

        # Limpiar campos de texto
        if "contenido" in internal_data:
            internal_data["contenido"] = limpiar_texto(internal_data["contenido"])

        return internal_data

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
