from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from datetime import datetime
import logging

from apps.proyectos.models import Proyecto
from apps.base.models import DetalleEnvio
from django.utils.timezone import now

logger = logging.getLogger(__name__)

class CapturaAlertasViewSet(viewsets.ViewSet):
    @action(detail=False, methods=['post'], url_path='capturar-alertas')
    def capturar_alertas(self, request):
        """
        Captura alertas recibidas vía JSON, valida duplicados por URL y proyecto,
        parsea fechas y devuelve resultado al front.
        """
        proyecto_id = request.data.get("proyecto_id")
        alertas = request.data.get("alertas", [])

        if not proyecto_id or not alertas:
            return Response({"error": "Se requieren 'proyecto_id' y 'alertas'"}, status=400)

        proyecto = get_object_or_404(Proyecto, id=proyecto_id)

        procesadas = []
        duplicadas = []

        for record in alertas:
            url = record.get("url")
            mensaje = record.get("contenido", "")
            fecha_str = record.get("fecha")
            fecha_pub = self._parse_fecha(fecha_str)

            # Validar duplicado por URL y proyecto
            alerta_existente = DetalleEnvio.objects.filter(url=url, proyecto=proyecto).first()
            if alerta_existente:
                duplicadas.append({
                    "id": alerta_existente.id,
                    "url": alerta_existente.url,
                    "mensaje": alerta_existente.mensaje
                })
                continue

            # Solo parseamos y preparamos para enviar al front
            procesadas.append({
                "id": alerta_existente.id,
                "url": alerta_existente.url,
                "mensaje": alerta_existente.mensaje,
                "fecha": alerta_existente.inicio_envio,
                "autor": alerta_existente.medio.autor if alerta_existente.medio else None,
                "reach": getattr(alerta_existente.medio, "reach", None),
                "engagement": getattr(alerta_existente.medio, "engagement", None),
                "red_social_id": alerta_existente.red_social.id if alerta_existente.red_social else None,
                "medio_id": alerta_existente.medio.id if alerta_existente.medio else None
            })

        return Response({
            "procesadas": procesadas,
            "duplicadas": duplicadas,
            "mensaje": f"{len(procesadas)} alertas procesadas, {len(duplicadas)} duplicadas."
        }, status=200)

    # -----------------------
    # Helpers internos
    # -----------------------
    def _parse_fecha(self, fecha_str: str):
        """Convierte un string ISO a datetime, o usa ahora si falla."""
        if not fecha_str:
            return now()
        try:
            return datetime.fromisoformat(fecha_str.replace("Z", "+00:00"))
        except Exception:
            logger.warning(f"Fecha inválida recibida: {fecha_str}, se usará ahora")
            return now()