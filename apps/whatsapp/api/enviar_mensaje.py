from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from datetime import datetime
import logging

from apps.base.models import DetalleEnvio, Articulo, Redes
from apps.proyectos.models import Proyecto

logger = logging.getLogger(__name__)


# -----------------------
# Clase base con helpers
# -----------------------
class BaseCapturaAlertasAPIView(APIView):
    """
    Clase base para captura de alertas (Medios / Redes).
    Define helpers comunes como parseo de fechas.
    """

    def _parse_fecha(self, fecha_str: str):
        """Convierte un string ISO a datetime, o usa ahora si falla."""
        if not fecha_str:
            return now()
        try:
            return datetime.fromisoformat(fecha_str.replace("Z", "+00:00"))
        except Exception:
            logger.warning(f"Fecha inválida recibida: {fecha_str}, se usará ahora")
            return now()


# -----------------------
# Medios
# -----------------------
class CapturaAlertasMediosAPIView(BaseCapturaAlertasAPIView):
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
            alerta_existente = DetalleEnvio.objects.filter(
                medio=record.get("id"), estado_enviado=True
            ).first()

            if alerta_existente:
                duplicadas.append({
                    "id": alerta_existente.id,
                    "id_articulo": record.get("id"),
                    "mensaje": alerta_existente.mensaje
                })
                continue

            titulo = record.get("titulo")
            mensaje = record.get("contenido", "")
            fecha_pub = self._parse_fecha(record.get("fecha"))
            autor = record.get("autor")
            reach = record.get("reach")

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
# Redes
# -----------------------
class CapturaAlertasRedesAPIView(BaseCapturaAlertasAPIView):
    """
    Captura alertas de Redes recibidas vía JSON, valida duplicados por URL y proyecto,
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
            alerta_existente = Redes.objects.filter(
                url=url, proyecto=proyecto
            ).first()

            if alerta_existente:
                duplicadas.append({
                    "id": alerta_existente.id,
                    "url": url,
                    "mensaje": record.get("contenido", "")
                })
                continue

            titulo = record.get("titulo")
            mensaje = record.get("contenido", "")
            fecha_pub = self._parse_fecha(record.get("fecha"))
            autor = record.get("autor")
            alcance = record.get("alcance")

            procesadas.append({
                "titulo": titulo,
                "url": url,
                "mensaje": mensaje,
                "fecha": fecha_pub,
                "autor": autor,
                "alcance": alcance
            })

        return Response({
            "procesadas": procesadas,
            "duplicadas": duplicadas,
            "mensaje": f"{len(procesadas)} alertas procesadas, {len(duplicadas)} duplicadas."
        }, status=200)
