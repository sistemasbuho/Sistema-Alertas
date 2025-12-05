from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
import json
import logging
import os
import time
from datetime import datetime
from urllib.parse import urljoin
import requests
from rest_framework import status
from django.utils import timezone
from collections.abc import Iterable
from typing import Optional, Tuple

from apps.base.api.utils import formatear_fecha_respuesta
from apps.base.models import DetalleEnvio, Articulo, Redes, TemplateConfig
from apps.proyectos.models import Proyecto
from django.contrib.auth import get_user_model

from apps.whatsapp.utils import ordenar_alertas_por_fecha


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


def _aplicar_estilos(
    valor: str, estilo: dict, *, etiqueta: Optional[str] = None
) -> Tuple[str, Optional[bool]]:
    """Aplica los estilos soportados por la plantilla al valor recibido."""

    valor_base = valor
    etiqueta_formateada = str(etiqueta) if etiqueta is not None else None

    if estilo:
        if estilo.get("negrita"):
            valor_base = f"*{valor_base}*"
            if etiqueta_formateada:
                etiqueta_formateada = f"*{etiqueta_formateada}*"
        if estilo.get("inclinado"):
            valor_base = f"_{valor_base}_"
            if etiqueta_formateada:
                etiqueta_formateada = f"_{etiqueta_formateada}_"

    salto_linea = estilo.get("salto_linea") if estilo else None
    valor_formateado = valor_base

    if etiqueta_formateada:
        # sin agregar ": ", solo concatenamos
        valor_formateado = f"{etiqueta_formateada}{valor_formateado}"

    return valor_formateado, salto_linea



def _obtener_fecha_legible(alerta: dict, *campos: str) -> str:
    """Devuelve la primera fecha legible disponible en los campos indicados."""

    for campo in campos:
        valor = alerta.get(campo)
        if valor in (None, ""):
            continue

        fecha_legible = formatear_fecha_respuesta(valor)
        if fecha_legible:
            return fecha_legible

        return str(valor)

    return ""


def _normalizar_emojis(emojis) -> str:
    """Devuelve un string con los emojis limpios o vacío si no hay información."""

    if emojis is None:
        return ""

    if isinstance(emojis, str):
        return emojis.strip()

    if isinstance(emojis, Iterable):
        partes = []
        for item in emojis:
            if item is None:
                continue
            texto = str(item).strip()
            if texto:
                partes.append(texto)
        return " ".join(partes)

    return str(emojis).strip()


def formatear_mensaje(alerta, plantilla, *, nombre_plantilla=None, tipo_alerta=None):
    """
    Genera un mensaje formateado aplicando la plantilla de estilos y orden.
    Funciona para alertas de medios o redes.
    """
    partes = []

    plantilla_objetivo = (nombre_plantilla or "").strip().lower()
    tipo_alerta_normalizado = (tipo_alerta or "").strip().lower()

    for campo, conf in sorted(plantilla.items(), key=lambda x: x[1].get("orden", 0)):
        valor = alerta.get(campo)
        if valor is None or valor == "":
            valor = alerta.get("mensaje")  # fallback a 'mensaje'

        if valor is None or valor == "":
            continue

        valor_str = str(valor)

        estilo = conf.get("estilo", {}) or {}
        valor_formateado, salto_linea = _aplicar_estilos(
            valor_str, estilo, etiqueta=conf.get("label")
        )
        partes.append((valor_formateado, salto_linea))

    mensaje = []
    for indice, (valor, salto_linea) in enumerate(partes):
        if indice > 0:
            if salto_linea is False:
                mensaje.append(" ")
            else:
                mensaje.append("\n")
        mensaje.append(valor)

    mensaje_final = "".join(mensaje)

    emojis_texto = _normalizar_emojis(alerta.get("emojis"))

    if emojis_texto and mensaje_final:
        lineas = mensaje_final.split("\n", 1) 
        primera = f"{emojis_texto} {lineas[0]}" 
        mensaje_final = (
            "\n".join([primera] + lineas[1:]) if len(lineas) > 1 else primera
        )
    elif emojis_texto:
        mensaje_final = emojis_texto

    return mensaje_final





def _enviar_muchos_en_uno(
    pendientes_envio,
    *,
    headers,
    url_mensaje,
    max_retries,
    retry_delay,
    grupo_id,
    enviados,
    no_enviados,
):
    """Envía un único mensaje concatenando varias alertas."""

    if not pendientes_envio:
        return

    cuerpo_mensaje = "\n\n".join(str(item.get("mensaje", "")) for item in pendientes_envio)
    payload = {"to": grupo_id, "body": cuerpo_mensaje, "no_link_preview": True}

    attempts = 0
    success = False
    while attempts < max_retries and not success:
        try:
            response = requests.post(url_mensaje, json=payload, headers=headers)
            if response.status_code == 200:
                timestamp = timezone.now()
                for item in pendientes_envio:
                    detalle_envio = item["detalle_envio"]
                    detalle_envio.fin_envio = timestamp
                    detalle_envio.estado_enviado = True
                    detalle_envio.save()
                    enviados.append(item["alerta_id"])
                success = True
            else:
                attempts += 1
                if attempts < max_retries:
                    time.sleep(retry_delay)
                else:
                    timestamp = timezone.now()
                    try:
                        detalle_respuesta = response.json()
                    except ValueError:
                        detalle_respuesta = response.text
                    for item in pendientes_envio:
                        detalle_envio = item["detalle_envio"]
                        detalle_envio.fin_envio = timestamp
                        detalle_envio.estado_enviado = False
                        detalle_envio.save()
                        no_enviados.append(
                            {
                                "alerta_id": item["alerta_id"],
                                "status_code": response.status_code,
                                "detalle": detalle_respuesta,
                            }
                        )
        except requests.RequestException as e:
            attempts += 1
            if attempts < max_retries:
                time.sleep(retry_delay)
            else:
                timestamp = timezone.now()
                for item in pendientes_envio:
                    detalle_envio = item["detalle_envio"]
                    detalle_envio.fin_envio = timestamp
                    detalle_envio.estado_enviado = False
                    detalle_envio.save()
                    no_enviados.append(
                        {
                            "alerta_id": item["alerta_id"],
                            "error": f"Error de conexión: {str(e)}",
                        }
                    )



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

        proyecto = get_object_or_404(Proyecto, id=proyecto_id)
        formato_muchos_en_uno = proyecto.formato_mensaje == "muchos en uno"

        # Obtener plantilla del proyecto
        plantilla = {}
        plantilla_nombre = None
        template_config = TemplateConfig.objects.filter(proyecto_id=proyecto_id).first()
        if template_config:
            plantilla = template_config.config_campos
            plantilla_nombre = template_config.nombre

        headers = {
            "Authorization": f"Bearer {self.access_key}",
            "Content-Type": "application/json",
        }

        enviados = []
        no_enviados = []
        pendientes_envio = []

        for alerta in alertas:
            alerta_id = alerta.get("id")  # id de la alerta en el JSON
            mensaje_original = alerta.get("contenido", "")
            titulo = alerta.get("titulo", "")
            autor = alerta.get("autor", "")
            fecha_legible = _obtener_fecha_legible(alerta, "fecha", "fecha_publicacion")

            if not alerta_id:
                no_enviados.append({"alerta_id": alerta_id, "error": "Falta ID de alerta"})
                continue

            # Preparamos los datos para el formateo
            alerta_data = {
                "titulo": titulo,
                "contenido": mensaje_original,
                "autor": autor,
                "fecha": fecha_legible,
                "emojis": alerta.get("emojis"),
            }

            # Formatear mensaje con la plantilla
            mensaje_formateado = formatear_mensaje(
                alerta_data,
                plantilla,
                nombre_plantilla=plantilla_nombre,
                tipo_alerta=tipo_alerta,
            )

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

            if formato_muchos_en_uno:
                pendientes_envio.append(
                    {
                        "alerta_id": alerta_id,
                        "detalle_envio": detalle_envio,
                        "mensaje": mensaje_formateado,
                    }
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

        if formato_muchos_en_uno:
            _enviar_muchos_en_uno(
                pendientes_envio,
                headers=headers,
                url_mensaje=self.url_mensaje,
                max_retries=self.max_retries,
                retry_delay=self.retry_delay,
                grupo_id=grupo_id,
                enviados=enviados,
                no_enviados=no_enviados,
            )

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
        plantilla_nombre = None
        template_config = TemplateConfig.objects.filter(proyecto=proyecto_id).first()
        if template_config:
            plantilla_mensaje = template_config.config_campos
            plantilla_nombre = template_config.nombre

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
                "alcance": alcance,
                "emojis": record.get("emojis"),
            })

            for alerta in procesadas:
                alerta["mensaje_formateado"] = formatear_mensaje(
                    alerta,
                    plantilla_mensaje,
                    nombre_plantilla=plantilla_nombre,
                    tipo_alerta="redes",
                )

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

        formato_muchos_en_uno = proyecto.formato_mensaje == "muchos en uno"

        # Obtener plantilla del proyecto
        plantilla = {}
        plantilla_nombre = None
        template_config = TemplateConfig.objects.filter(proyecto_id=proyecto_id).first()
        if template_config:
            plantilla = template_config.config_campos
            plantilla_nombre = template_config.nombre

        headers = {
            "Authorization": f"Bearer {self.access_key}",
            "Content-Type": "application/json",
        }

        enviados = []
        no_enviados = []

        # Log detallado del payload recibido
        print("=" * 80)
        print("=== PAYLOAD RECIBIDO ===")
        print(f"Total alertas: {len(alertas)}")
        for i, a in enumerate(alertas[:5]):
            print(f"Alerta {i}: id={a.get('id')}")
            print(f"  fecha={a.get('fecha')}")
            print(f"  fecha_publicacion={a.get('fecha_publicacion')}")
        print("=" * 80)

        # Ordenar alertas
        alertas = ordenar_alertas_por_fecha(alertas)

        # Log después de ordenar
        print("=" * 80)
        print("=== DESPUÉS DE ORDENAR ===")
        for i, a in enumerate(alertas[:5]):
            print(f"Alerta {i}: id={a.get('id')}")
            print(f"  fecha={a.get('fecha')}")
            print(f"  fecha_publicacion={a.get('fecha_publicacion')}")
        print("=" * 80)

        pendientes_envio = []

        for alerta in alertas:
            alerta_id = alerta.get("id")
            url = alerta.get("url")
            mensaje_original = alerta.get("contenido", "")
            titulo = alerta.get("titulo", "")
            autor = alerta.get("autor", "")
            fecha_legible = _obtener_fecha_legible(alerta, "fecha", "fecha_publicacion")
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
                "fecha_publicacion": fecha_legible,
                "reach" : reach,
                "engagement" :engagement,
                "emojis": alerta.get("emojis"),

            }

            mensaje_formateado = formatear_mensaje(
                alerta_data,
                plantilla,
                nombre_plantilla=plantilla_nombre,
                tipo_alerta=tipo_alerta,
            )
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

            if formato_muchos_en_uno:
                pendientes_envio.append(
                    {
                        "alerta_id": alerta_id,
                        "detalle_envio": detalle_envio,
                        "mensaje": mensaje_formateado,
                    }
                )
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

        if formato_muchos_en_uno:
            _enviar_muchos_en_uno(
                pendientes_envio,
                headers=headers,
                url_mensaje=self.url_mensaje,
                max_retries=self.max_retries,
                retry_delay=self.retry_delay,
                grupo_id=grupo_id,
                enviados=enviados,
                no_enviados=no_enviados,
            )

        payload_monitoreo = {}
        if hasattr(request.data, "items"):
            for key, value in request.data.items():
                payload_monitoreo[key] = value
        else:
            payload_monitoreo = dict(request.data)
        payload_monitoreo["alertas"] = alertas

        monitoreo_result = enviar_alertas_a_monitoreo(
            proyecto_id=proyecto_id,
            tipo_alerta=tipo_alerta,
            data_alertas=payload_monitoreo,
            enviados_ids=enviados,
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

    formato_muchos_en_uno = proyecto.formato_mensaje == "muchos en uno"

    # Obtener plantilla del proyecto
    plantilla = {}
    plantilla_nombre = None
    template_config = TemplateConfig.objects.filter(proyecto_id=proyecto_id).first()
    if template_config:
        plantilla = template_config.config_campos
        plantilla_nombre = template_config.nombre

    User = get_user_model()
    usuario = User.objects.get(id=usuario_id)

    headers = {
        "Authorization": f"Bearer {access_key}",
        "Content-Type": "application/json",
    }

    enviados = []
    no_enviados = []
    pendientes_envio = []

    for alerta in alertas:
        alerta_id = alerta.get("id")
        url = alerta.get("url")
        mensaje_original = alerta.get("contenido", "")
        titulo = alerta.get("titulo", "")
        autor = alerta.get("autor", "")
        fecha_legible = _obtener_fecha_legible(alerta, "fecha", "fecha_publicacion")
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
            "fecha_publicacion": fecha_legible,
            "reach": reach,
            "engagement": engagement,
            "emojis": alerta.get("emojis"),
        }
        mensaje_formateado = formatear_mensaje(
            alerta_data,
            plantilla,
            nombre_plantilla=plantilla_nombre,
            tipo_alerta=tipo_alerta,
        )

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

        if formato_muchos_en_uno:
            pendientes_envio.append(
                {
                    "alerta_id": alerta_id,
                    "detalle_envio": detalle_envio,
                    "mensaje": mensaje_formateado,
                }
            )
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

    if formato_muchos_en_uno:
        _enviar_muchos_en_uno(
            pendientes_envio,
            headers=headers,
            url_mensaje=url_mensaje,
            max_retries=max_retries,
            retry_delay=retry_delay,
            grupo_id=grupo_id,
            enviados=enviados,
            no_enviados=no_enviados,
        )

    payload_monitoreo = {"alertas": alertas}

    monitoreo_result = enviar_alertas_a_monitoreo(
        proyecto_id=proyecto_id,
        tipo_alerta=tipo_alerta,
        data_alertas=payload_monitoreo,
        enviados_ids=enviados,
        grupo_id=grupo_id,
    )

    return {
        "success": f"Se enviaron {len(enviados)} alertas",
        "enviados": enviados,
        "no_enviados": no_enviados,
        "monitoreo": monitoreo_result,
    }


def enviar_alertas_a_monitoreo(proyecto_id, tipo_alerta, data_alertas, enviados_ids=None, grupo_id=None):
    """Envía la información de alertas al servicio de monitoreo externo."""
    if not data_alertas:
        return {"detalle": "Sin alertas para enviar"}

    alertas = data_alertas.get("alertas", [])
    if not alertas:
        return {"detalle": "Sin alertas para enviar"}

    enviados_ids = set(enviados_ids or [])
    alertas_enviadas = [alerta for alerta in alertas if alerta.get("id") in enviados_ids]
    if not alertas_enviadas:
        return {"detalle": "Sin alertas para enviar"}

    base_url = os.getenv("MONITOREO_API_URL", "https://monitoreo.buho.media/")
    endpoint = os.getenv("MONITOREO_API_ENDPOINT", "api/alertas/")
    url = urljoin(base_url, endpoint)

    payload = {
        "proyecto_id": proyecto_id,
        "tipo_alerta": tipo_alerta,
        "alertas": alertas_enviadas,
    }

    proveedor = data_alertas.get("proveedor")
    if proveedor:
        payload["proveedor"] = proveedor

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