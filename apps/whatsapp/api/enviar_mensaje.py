from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from datetime import datetime
import logging
import os
import requests  
from rest_framework import status
from django.utils import timezone

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
                "id" : record.get("id"),
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
                "id" : record.get("id"),
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


# -----------------------
# WHAPI
# -----------------------

class EnviarMensajeAPIView(APIView):
    access_key = os.getenv("WHAPI_TOKEN")
    url_mensaje = "https://gate.whapi.cloud/messages/text"
    max_retries = 3
    retry_delay = 2

class EnviarMensajeAPIView(APIView):
    access_key = os.getenv("WHAPI_TOKEN")
    url_mensaje = "https://gate.whapi.cloud/messages/text"
    max_retries = 3
    retry_delay = 2

    def post(self, request):
        proyecto_id = request.data.get("proyecto_id")
        grupo_id = request.data.get("grupo_id")
        tipo_alerta = request.data.get("tipo_alerta")  # medio | redes
        alertas = request.data.get("alertas", [])

        if not proyecto_id or not grupo_id or not tipo_alerta or not alertas:
            return Response(
                {"error": "Se requieren 'proyecto_id', 'grupo_id', 'tipo_alerta' y 'alertas'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if tipo_alerta not in ["medio", "redes"]:
            return Response(
                {"error": "El campo 'tipo_alerta' debe ser 'medio' o 'redes'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        headers = {
            "Authorization": f"Bearer {self.access_key}",
            "Content-Type": "application/json",
        }

        enviados = []
        no_enviados = []

        for alerta in alertas:
            publicacion_id = alerta.get("publicacion_id")
            mensaje = alerta.get("mensaje")

            if not publicacion_id or not mensaje:
                no_enviados.append(
                    {"publicacion_id": publicacion_id, "error": "Faltan datos en la alerta"}
                )
                continue

            # Definir filtros para update_or_create
            filtros = {}
            if tipo_alerta == "medio":
                filtros["medio_id"] = publicacion_id
            elif tipo_alerta == "redes":
                filtros["red_social_id"] = publicacion_id

            detalle_envio, _ = DetalleEnvio.objects.update_or_create(
                **filtros,
                defaults={
                    "inicio_envio": timezone.now(),
                    "mensaje": mensaje,
                    "usuario": request.user if request.user.is_authenticated else None,
                },
            )

            payload = {
                "to": grupo_id,
                "body": mensaje,
                "no_link_preview": True,
            }

            success = False
            attempts = 0
            while attempts < self.max_retries and not success:
                try:
                    response = requests.post(self.url_mensaje, json=payload, headers=headers)

                    if response.status_code == 200:
                        detalle_envio.fin_envio = timezone.now()
                        detalle_envio.estado_enviado = True
                        detalle_envio.save()
                        enviados.append(publicacion_id)
                        success = True
                    else:
                        attempts += 1
                        if attempts < self.max_retries:
                            time.sleep(self.retry_delay)
                        else:
                            detalle_envio.fin_envio = timezone.now()
                            detalle_envio.estado_enviado = False
                            detalle_envio.save()
                            no_enviados.append(
                                {
                                    "publicacion_id": publicacion_id,
                                    "status_code": response.status_code,
                                    "detalle": response.json(),
                                }
                            )
                except requests.RequestException as e:
                    attempts += 1
                    if attempts < self.max_retries:
                        time.sleep(self.retry_delay)
                    else:
                        detalle_envio.fin_envio = timezone.now()
                        detalle_envio.estado_enviado = False
                        detalle_envio.save()
                        no_enviados.append(
                            {"publicacion_id": publicacion_id, "error": f"Error de conexión: {str(e)}"}
                        )

        return Response(
            {
                "success": f"Se enviaron {len(enviados)} alertas",
                "enviados": enviados,
                "no_enviados": no_enviados,
            },
            status=status.HTTP_200_OK,
        )