from rest_framework import serializers

from apps.base.models import DetalleEnvio

from .serializer_evaluacion import EvaluacionIAResumenSerializer


class AlertaExcepcionSerializer(serializers.ModelSerializer):
    """Item de la cola de excepciones: la alerta + sugerencias de la IA +
    preview del mensaje WhatsApp, todo pre-resuelto para decisión rápida (D4)."""

    alerta_id = serializers.SerializerMethodField()
    tipo = serializers.SerializerMethodField()
    proyecto_nombre = serializers.CharField(source="proyecto.nombre", read_only=True)
    proyecto_keywords = serializers.SerializerMethodField()
    titulo = serializers.SerializerMethodField()
    contenido = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    autor = serializers.SerializerMethodField()
    ubicacion = serializers.SerializerMethodField()
    fecha_publicacion = serializers.SerializerMethodField()
    reach = serializers.SerializerMethodField()
    engagement = serializers.SerializerMethodField()
    red_social_nombre = serializers.SerializerMethodField()
    mensaje_formateado = serializers.SerializerMethodField()
    evaluacion_ia = serializers.SerializerMethodField()

    class Meta:
        model = DetalleEnvio
        fields = [
            "id",
            "alerta_id",
            "tipo",
            "proyecto",
            "proyecto_nombre",
            "proyecto_keywords",
            "titulo",
            "contenido",
            "url",
            "autor",
            "ubicacion",
            "fecha_publicacion",
            "reach",
            "engagement",
            "red_social_nombre",
            "estado_pipeline",
            "mensaje_formateado",
            "evaluacion_ia",
            "created_at",
        ]

    def _objeto(self, obj):
        return obj.red_social or obj.medio

    def get_alerta_id(self, obj):
        objeto = self._objeto(obj)
        return str(objeto.id) if objeto else None

    def get_tipo(self, obj):
        return "redes" if obj.red_social_id else "medios"

    def get_proyecto_keywords(self, obj):
        if obj.proyecto and hasattr(obj.proyecto, "get_keywords_list"):
            return obj.proyecto.get_keywords_list()
        return []

    def get_titulo(self, obj):
        return getattr(self._objeto(obj), "titulo", None)

    def get_contenido(self, obj):
        objeto = self._objeto(obj)
        return objeto.contenido if objeto else None

    def get_url(self, obj):
        objeto = self._objeto(obj)
        return objeto.url if objeto else None

    def get_autor(self, obj):
        objeto = self._objeto(obj)
        return objeto.autor if objeto else None

    def get_ubicacion(self, obj):
        objeto = self._objeto(obj)
        return objeto.ubicacion if objeto else None

    def get_fecha_publicacion(self, obj):
        objeto = self._objeto(obj)
        return objeto.fecha_publicacion if objeto else None

    def get_reach(self, obj):
        objeto = self._objeto(obj)
        return objeto.reach if objeto else None

    def get_engagement(self, obj):
        objeto = self._objeto(obj)
        return objeto.engagement if objeto else None

    def get_red_social_nombre(self, obj):
        if obj.red_social and obj.red_social.red_social:
            return obj.red_social.red_social.nombre
        return None

    def get_evaluacion_ia(self, obj):
        evaluacion = obj.evaluaciones_ia.order_by("-created_at").first()
        return EvaluacionIAResumenSerializer(evaluacion).data if evaluacion else None

    def get_mensaje_formateado(self, obj):
        """Preview del mensaje final (con emojis propuestos por la IA)."""
        from apps.base.models import TemplateConfig
        from apps.whatsapp.api.enviar_mensaje import formatear_mensaje
        from apps.whatsapp.services.envio import componer_emojis

        objeto = self._objeto(obj)
        if objeto is None or obj.proyecto is None:
            return None

        matriz = getattr(obj.proyecto, "matriz_ia", None)
        evaluacion = obj.evaluaciones_ia.order_by("-created_at").first()
        template = TemplateConfig.objects.filter(proyecto=obj.proyecto).first()
        try:
            return formatear_mensaje(
                {
                    "url": objeto.url,
                    "titulo": getattr(objeto, "titulo", None),
                    "contenido": objeto.contenido,
                    "autor": objeto.autor,
                    "fecha_publicacion": str(objeto.fecha_publicacion or ""),
                    "reach": objeto.reach,
                    "engagement": objeto.engagement,
                    "ubicacion": objeto.ubicacion,
                    "emojis": componer_emojis(matriz, evaluacion),
                },
                template.config_campos if template else {},
                nombre_plantilla=template.nombre if template else None,
                tipo_alerta=self.get_tipo(obj),
                keywords=self.get_proyecto_keywords(obj),
            )
        except Exception:  # pylint: disable=broad-except
            return None
