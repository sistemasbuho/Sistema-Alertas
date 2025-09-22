from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from datetime import datetime
import logging
import os
from urllib.parse import urljoin
import requests
from rest_framework import status
from django.utils import timezone

from apps.base.models import DetalleEnvio, Articulo, Redes, TemplateConfig
from apps.proyectos.models import Proyecto
from django.contrib.auth import get_user_model


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


def formatear_mensaje(alerta, plantilla):
    """
    Genera un mensaje formateado aplicando la plantilla de estilos y orden.
    Funciona para alertas de medios o redes.
    """
    partes = []

    for campo, conf in sorted(plantilla.items(), key=lambda x: x[1].get('orden', 0)):
        valor = alerta.get(campo) or alerta.get('mensaje')  # fallback a 'mensaje'
        if not valor:
            continue

        estilo = conf.get('estilo', {})
        if estilo.get('negrita'):
            valor = f"*{valor}*"
        if estilo.get('inclinado'):
            valor = f"_{valor}_"

        partes.append(valor)

    return "\n".join(partes)



# -----------------------
# Medios
# -----------------------
class CapturaAlertasMediosAPIView(BaseCapturaAlertasAPIView):
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

        # Obtener plantilla del proyecto
        plantilla = {}
        template_config = TemplateConfig.objects.filter(proyecto_id=proyecto_id).first()
        if template_config:
            plantilla = template_config.config_campos

        headers = {
            "Authorization": f"Bearer {self.access_key}",
            "Content-Type": "application/json",
        }

        enviados = []
        no_enviados = []

        for alerta in alertas:
            alerta_id = alerta.get("id")  # id de la alerta en el JSON
            mensaje_original = alerta.get("contenido", "")
            titulo = alerta.get("titulo", "")
            autor = alerta.get("autor", "")
            fecha = alerta.get("fecha", "")

            if not alerta_id:
                no_enviados.append({"alerta_id": alerta_id, "error": "Falta ID de alerta"})
                continue

            # Preparamos los datos para el formateo
            alerta_data = {
                "titulo": titulo,
                "contenido": mensaje_original,
                "autor": autor,
                "fecha": fecha,
            }

            # Formatear mensaje con la plantilla
            mensaje_formateado = formatear_mensaje(alerta_data, plantilla)

            # Crear o actualizar detalle de envío
            filtros = {"proyecto_id": proyecto_id}
            if tipo_alerta == "medio":
                filtros["medio_id"] = alerta_id
            else:
                filtros["red_social_id"] = alerta_id

            detalle_envio, _ = DetalleEnvio.objects.update_or_create(
                **filtros,
                defaults={
                    "inicio_envio": timezone.now(),
                    "mensaje": mensaje_formateado,
                    "usuario": request.user if request.user.is_authenticated else None,
                    "proyecto_id": proyecto_id,
                },
            )

            # Si ya fue enviado, no lo reenviamos
            if detalle_envio.estado_enviado:
                no_enviados.append(
                    {"alerta_id": alerta_id, "error": "Ya fue enviada anteriormente"}
                )
                continue

            # Armar payload para WhatsApp
            payload = {"to": grupo_id, "body": mensaje_formateado, "no_link_preview": True}

            success = False
            attempts = 0
            while attempts < self.max_retries and not success:
                try:
                    response = requests.post(self.url_mensaje, json=payload, headers=headers)
                    if response.status_code == 200:
                        detalle_envio.fin_envio = timezone.now()
                        detalle_envio.estado_enviado = True
                        detalle_envio.save()
                        enviados.append(alerta_id)
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
                                    "alerta_id": alerta_id,
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
                        no_enviados.append({"alerta_id": alerta_id, "error": f"Error de conexión: {str(e)}"})

        return Response(
            {
                "success": f"Se enviaron {len(enviados)} alertas",
                "enviados": enviados,
                "no_enviados": no_enviados,
                "plantilla_usada": plantilla,
            },
            status=status.HTTP_200_OK,
        )


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
        
        plantilla_mensaje = {}
        template_config = TemplateConfig.objects.filter(proyecto=proyecto_id).first()
        if template_config:
            plantilla_mensaje = template_config.config_campos 

        procesadas = []
        duplicadas = []

        for record in alertas:
            url = record.get("url")
            alerta_existente = DetalleEnvio.objects.filter(
                red_social_id=record.get("id"), estado_enviado=True,proyecto_id=proyecto
            ).first()


            print('alerta_existente',alerta_existente)

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

            for alerta in procesadas:
                alerta["mensaje_formateado"] = formatear_mensaje(alerta, plantilla_mensaje) 

        return Response({
            "procesadas": procesadas,
            "duplicadas": duplicadas,
            "mensaje": f"{len(procesadas)} alertas procesadas, {len(duplicadas)} duplicadas.",
            "plantilla_mensaje": plantilla_mensaje,
            "codigo_acceso": proyecto.codigo_acceso  
        }, status=200)

# -----------------------
# Nota revisada
# -----------------------
class MarcarRevisadoAPIView(APIView):
    """
    Marca como revisadas las alertas enviadas, según su tipo y sus IDs.
    """

    def post(self, request):
        tipo_alerta = request.data.get("tipo_alerta")  # medio | redes
        alertas = request.data.get("alertas", [])

        if not tipo_alerta or not alertas:
            return Response(
                {"error": "Se requieren 'tipo_alerta' y 'alertas'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if tipo_alerta not in ["medios", "redes"]:
            return Response(
                {"error": "El campo 'tipo_alerta' debe ser 'medio' o 'redes'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        actualizados = []
        no_encontrados = []

        for alerta in alertas:
            alerta_id = alerta.get("id")
            if not alerta_id:
                no_encontrados.append({"id": None, "error": "Falta ID de alerta"})
                continue

            filtros = {}
            if tipo_alerta == "medios":
                filtros["medio_id"] = alerta_id
            else:  
                filtros["red_social_id"] = alerta_id

            detalle_qs = DetalleEnvio.objects.filter(**filtros)
            if detalle_qs.exists():
                detalle_qs.update(estado_revisado=True, modified_at=timezone.now())
                actualizados.append(alerta_id)
            else:
                no_encontrados.append({"id": alerta_id, "error": "No se encontró la alerta"})

        return Response(
            {
                "actualizados": actualizados,
                "no_encontrados": no_encontrados,
            },
            status=status.HTTP_200_OK
        )

# -----------------------
# WHAPI
# -----------------------

class EnviarMensajeAPIView(APIView):
    access_key = os.getenv("WHAPI_TOKEN")
    url_mensaje = "https://gate.whapi.cloud/messages/text"
    max_retries = 3
    retry_delay = 2

    def post(self, request):
        proyecto_id = request.data.get("proyecto_id")
        tipo_alerta = request.data.get("tipo_alerta")  # medios | redes
        alertas = request.data.get("alertas", [])

        if not proyecto_id or not tipo_alerta or not alertas:
            return Response(
                {"error": "Se requieren 'proyecto_id', 'tipo_alerta' y 'alertas'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if tipo_alerta not in ["medios", "redes"]:
            return Response(
                {"error": "El campo 'tipo_alerta' debe ser 'medio' o 'redes'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Obtener grupo_id automáticamente desde el proyecto
        try:
            proyecto = Proyecto.objects.get(id=proyecto_id)
            grupo_id = proyecto.codigo_acceso  # ⚡ Asegúrate de que tu modelo tenga este campo
        except Proyecto.DoesNotExist:
            return Response(
                {"error": "Proyecto no existe"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Obtener plantilla del proyecto
        plantilla = {}
        template_config = TemplateConfig.objects.filter(proyecto_id=proyecto_id).first()
        if template_config:
            plantilla = template_config.config_campos

        headers = {
            "Authorization": f"Bearer {self.access_key}",
            "Content-Type": "application/json",
        }

        enviados = []
        no_enviados = []

        for alerta in alertas:
            alerta_id = alerta.get("id")
            url = alerta.get("url")
            mensaje_original = alerta.get("contenido", "")
            titulo = alerta.get("titulo", "")
            autor = alerta.get("autor", "")
            fecha = alerta.get("fecha", "")
            reach = alerta.get("reach", "")
            engagement = alerta.get("engagement", "")




            if not alerta_id:
                no_enviados.append({"alerta_id": alerta_id, "error": "Falta ID de alerta"})
                continue

            alerta_data = {
                "url" : url,
                "titulo": titulo,
                "contenido": mensaje_original,
                "autor": autor,
                "fecha_publicacion": fecha,
                "reach" : reach,
                "engagement" :engagement

            }
            mensaje_formateado = formatear_mensaje(alerta_data, plantilla)
            filtros = {"proyecto_id": proyecto_id}
            if tipo_alerta == "medios":
                filtros["medio_id"] = alerta_id
            else:
                filtros["red_social_id"] = alerta_id

            detalle_envio, _ = DetalleEnvio.objects.update_or_create(
                **filtros,
                defaults={
                    "inicio_envio": timezone.now(),
                    "mensaje": mensaje_formateado,
                    "usuario": request.user if request.user.is_authenticated else None,
                    "proyecto_id": proyecto_id,
                },
            )

            if detalle_envio.estado_enviado:
                no_enviados.append({"alerta_id": alerta_id, "error": "Ya fue enviada anteriormente"})
                continue

            payload = {"to": grupo_id, "body": mensaje_formateado, "no_link_preview": True}

            success = False
            attempts = 0
            while attempts < self.max_retries and not success:
                try:
                    response = requests.post(self.url_mensaje, json=payload, headers=headers)
                    if response.status_code == 200:
                        detalle_envio.fin_envio = timezone.now()
                        detalle_envio.estado_enviado = True
                        detalle_envio.save()
                        enviados.append(alerta_id)
                        success = True
                    else:
                        attempts += 1
                        if attempts < self.max_retries:
                            time.sleep(self.retry_delay)
                        else:
                            detalle_envio.fin_envio = timezone.now()
                            detalle_envio.estado_enviado = False
                            detalle_envio.save()
                            no_enviados.append({
                                "alerta_id": alerta_id,
                                "status_code": response.status_code,
                                "detalle": response.json(),
                            })
                except requests.RequestException as e:
                    attempts += 1
                    if attempts < self.max_retries:
                        time.sleep(self.retry_delay)
                    else:
                        detalle_envio.fin_envio = timezone.now()
                        detalle_envio.estado_enviado = False
                        detalle_envio.save()
                        no_enviados.append({"alerta_id": alerta_id, "error": f"Error de conexión: {str(e)}"})

        alertas_enviadas = [alerta for alerta in alertas if alerta.get("id") in enviados]
        monitoreo_result = enviar_alertas_a_monitoreo(
            proyecto_id=proyecto_id,
            tipo_alerta=tipo_alerta,
            alertas=alertas_enviadas,
            grupo_id=grupo_id,
        )

        return Response({
            "success": f"Se enviaron {len(enviados)} alertas",
            "enviados": enviados,
            "no_enviados": no_enviados,
            "monitoreo": monitoreo_result,
        }, status=status.HTTP_200_OK)



def enviar_alertas_automatico(proyecto_id, tipo_alerta, alertas, usuario_id=2):
    """
    Envía alertas automáticamente simulando lo que hace EnviarMensajeAPIView.post
    """
    access_key = os.getenv("WHAPI_TOKEN")
    url_mensaje = "https://gate.whapi.cloud/messages/text"
    max_retries = 3
    retry_delay = 2

    if not proyecto_id or not tipo_alerta or not alertas:
        return {"error": "Se requieren 'proyecto_id', 'tipo_alerta' y 'alertas'"}

    if tipo_alerta not in ["medios", "redes"]:
        return {"error": "El campo 'tipo_alerta' debe ser 'medios' o 'redes'"}

    # Obtener proyecto y grupo_id
    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
        grupo_id = proyecto.codigo_acceso
    except Proyecto.DoesNotExist:
        return {"error": "Proyecto no existe"}

    # Obtener plantilla del proyecto
    plantilla = {}
    template_config = TemplateConfig.objects.filter(proyecto_id=proyecto_id).first()
    if template_config:
        plantilla = template_config.config_campos

    User = get_user_model()
    usuario = User.objects.get(id=usuario_id)

    headers = {
        "Authorization": f"Bearer {access_key}",
        "Content-Type": "application/json",
    }

    enviados = []
    no_enviados = []

    for alerta in alertas:
        alerta_id = alerta.get("id")
        url = alerta.get("url")
        mensaje_original = alerta.get("contenido", "")
        titulo = alerta.get("titulo", "")
        autor = alerta.get("autor", "")
        fecha = alerta.get("fecha", "")
        reach = alerta.get("reach", "")
        engagement = alerta.get("engagement", "")

        if not alerta_id:
            no_enviados.append({"alerta_id": alerta_id, "error": "Falta ID de alerta"})
            continue

        # Formatear mensaje
        alerta_data = {
            "url": url,
            "titulo": titulo,
            "contenido": mensaje_original,
            "autor": autor,
            "fecha_publicacion": fecha,
            "reach": reach,
            "engagement": engagement,
        }
        mensaje_formateado = formatear_mensaje(alerta_data, plantilla)

        # Crear o actualizar detalle de envío
        filtros = {"proyecto_id": proyecto_id}
        if tipo_alerta == "medios":
            filtros["medio_id"] = alerta_id
        else:
            filtros["red_social_id"] = alerta_id

        detalle_envio, _ = DetalleEnvio.objects.update_or_create(
            **filtros,
            defaults={
                "inicio_envio": timezone.now(),
                "mensaje": mensaje_formateado,
                "usuario": usuario,
                "proyecto_id": proyecto_id,
            },
        )

        if detalle_envio.estado_enviado:
            no_enviados.append({"alerta_id": alerta_id, "error": "Ya fue enviada anteriormente"})
            continue

        payload = {"to": grupo_id, "body": mensaje_formateado, "no_link_preview": True}

        # Reintentos
        success = False
        attempts = 0
        while attempts < max_retries and not success:
            try:
                response = requests.post(url_mensaje, json=payload, headers=headers)
                if response.status_code == 200:
                    detalle_envio.fin_envio = timezone.now()
                    detalle_envio.estado_enviado = True
                    detalle_envio.save()
                    enviados.append(alerta_id)
                    success = True
                else:
                    attempts += 1
                    if attempts < max_retries:
                        time.sleep(retry_delay)
                    else:
                        detalle_envio.fin_envio = timezone.now()
                        detalle_envio.estado_enviado = False
                        detalle_envio.save()
                        no_enviados.append({
                            "alerta_id": alerta_id,
                            "status_code": response.status_code,
                            "detalle": response.json(),
                        })
            except requests.RequestException as e:
                attempts += 1
                if attempts < max_retries:
                    time.sleep(retry_delay)
                else:
                    detalle_envio.fin_envio = timezone.now()
                    detalle_envio.estado_enviado = False
                    detalle_envio.save()
                    no_enviados.append({"alerta_id": alerta_id, "error": f"Error de conexión: {str(e)}"})

    alertas_enviadas = [alerta for alerta in alertas if alerta.get("id") in enviados]
    monitoreo_result = enviar_alertas_a_monitoreo(
        proyecto_id=proyecto_id,
        tipo_alerta=tipo_alerta,
        alertas=alertas_enviadas,
        grupo_id=grupo_id,
    )

    return {
        "success": f"Se enviaron {len(enviados)} alertas",
        "enviados": enviados,
        "no_enviados": no_enviados,
        "monitoreo": monitoreo_result,
    }


def enviar_alertas_a_monitoreo(proyecto_id, tipo_alerta, alertas, grupo_id=None):
    """Envía la información de alertas al servicio de monitoreo externo."""
    if not alertas:
        return {"detalle": "Sin alertas para enviar"}

    base_url = os.getenv("MONITOREO_API_URL", "https://monitoreo.buho.media/")
    endpoint = os.getenv("MONITOREO_API_ENDPOINT", "api/alertas/")
    url = urljoin(base_url, endpoint)

    payload = {
        "proyecto_id": proyecto_id,
        "tipo_alerta": tipo_alerta,
        "alertas": alertas,
    }

    if grupo_id:
        payload["grupo_id"] = grupo_id

    headers = {"Content-Type": "application/json"}
    token = os.getenv("MONITOREO_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.Timeout:
        logger.error("Timeout al enviar alertas al servicio de monitoreo", exc_info=True)
        return {"error": "timeout"}
    except requests.HTTPError as exc:
        logger.error(
            "Respuesta inesperada del servicio de monitoreo", exc_info=True
        )
        return {"error": "http_error", "status_code": exc.response.status_code, "detalle": exc.response.text}
    except requests.RequestException:
        logger.error("No fue posible contactar el servicio de monitoreo", exc_info=True)
        return {"error": "conexion"}

    try:
        return response.json()
    except ValueError:
        return {"status": "ok", "status_code": response.status_code}