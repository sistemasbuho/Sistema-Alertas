from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from datetime import datetime
import logging

from apps.proyectos.models import Proyecto
from apps.base.models import DetalleEnvio
from django.utils.timezone import now
from rest_framework.views import APIView


logger = logging.getLogger(__name__)

class CapturaAlertasMediosAPIView(APIView):
    """
    Captura alertas recibidas vía JSON, valida duplicados por URL y proyecto,
    parsea fechas y devuelve resultado al front.
    """

    def post(self, request):
        proyecto_id = request.data.get("proyecto_id")
        alertas = request.data.get("alertas", [])

        if not proyecto_id or not alertas:
            return Response({"error": "Se requieren 'proyecto_id' y 'alertas'"}, status=400)

        proyecto = get_object_or_404(Proyecto, id=proyecto_id)

        procesadas = []
        duplicadas = []

        for record in alertas:
            url = record.get("url")
            alerta_existente = DetalleEnvio.objects.filter(medio=record.get("id"),estado_enviado=True).first()
            if alerta_existente:
                duplicadas.append({
                    "id": alerta_existente.id,
                    "id_articulo": record.get("id"),
                    "mensaje": alerta_existente.mensaje
                })
                continue

            # Ajustar la alerta que sí pasa
            titulo = record.get("titulo")
            mensaje = record.get("contenido", "")
            fecha_str = record.get("fecha")
            fecha_pub = self._parse_fecha(fecha_str)
            autor = record.get("autor")
            reach = record.get("reach")

            # Solo parseamos y preparamos para enviar al front
            procesadas.append({
                "titulo": titulo,
                "url": url,
                "mensaje": mensaje,
                "fecha": fecha_pub,
                "autor": autor,
                "reach": reach
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