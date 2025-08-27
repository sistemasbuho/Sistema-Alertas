import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
import tldextract
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Usuario, Proyecto, Datos
from .utils.format_message import parse_date, format_message_db, format_message_user_config
from dotenv import load_dotenv

# Config
load_dotenv()
ACCESS_KEY = os.getenv("WHAPI_TOKEN")
WHAPI_URL = "https://gate.whapi.cloud"
MAX_RETRIES = 3
RETRY_DELAY = 2
BATCH_SIZE = 6

logger = logging.getLogger(__name__)


@api_view(["POST"])
def automatic_send(request):
    """
    Procesa registros recibidos vía JSON y los envía automáticamente a WhatsApp.
    """
    start_time = datetime.now()

    proyecto_id = request.data.get("proyecto_id")
    new_records = request.data.get("new_records", [])
    repeated_records = request.data.get("repeated_records", [])
    invalid_records = request.data.get("records_QT_invalidos", [])

    if not proyecto_id or not new_records:
        return Response(
            {"error": "Se requieren 'proyecto_id' y 'new_records'"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    proyecto = get_object_or_404(Proyecto, id=proyecto_id)
    usuario = get_object_or_404(Usuario, email=request.user.email)

    if not _grupo_existe(proyecto.id_acceso_whatsapp):
        return Response({"error": "El grupo no existe"}, status=status.HTTP_404_NOT_FOUND)

    if proyecto.tipo_envio != "Automático":
        return Response({"mensaje": "El proyecto no está en modo automático."}, status=200)

    status_list = []
    sent_count = 0
    send_state = True

    # Guardar inválidos
    for record in invalid_records:
        _guardar_registro(record, proyecto, usuario, start_time, enviado=False)
        status_list.append("No Enviado")

    # Procesar válidos
    mensajes_grupales = []
    for idx, record in enumerate(sort_records(new_records)):
        try:
            mensaje, fecha_publicacion, url_auto = _preparar_registro(record, proyecto)

            if proyecto.formato_mensaje == "Uno por Uno":
                if not _enviar_y_guardar(mensaje, proyecto.id_acceso_whatsapp, url_auto, fecha_publicacion,
                                         proyecto, usuario, start_time, status_list):
                    send_state = False
                    break
                sent_count += 1

            elif proyecto.formato_mensaje == "Muchos en Uno":
                mensajes_grupales.append(format_message_user_config(record, proyecto))
                if len(mensajes_grupales) == BATCH_SIZE or idx == len(new_records) - 1:
                    batch_msg = "\n".join(mensajes_grupales)
                    if not _enviar_y_guardar(batch_msg, proyecto.id_acceso_whatsapp, url_auto, fecha_publicacion,
                                             proyecto, usuario, start_time, status_list):
                        send_state = False
                        break
                    sent_count += len(mensajes_grupales)
                    mensajes_grupales.clear()

        except Exception as e:
            logger.exception(f"Error procesando record {record}: {e}")
            continue

    return Response(
        {
            "send_error": not send_state,
            "status_auto": status_list,
            "sent_count": sent_count,
            "duplicated_count": len(repeated_records),
            "mensaje": f"{len(new_records)} nuevos registros procesados automáticamente.",
        },
        status=status.HTTP_200_OK if send_state else status.HTTP_400_BAD_REQUEST,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _grupo_existe(group_id: str) -> bool:
    url = f"{WHAPI_URL}/groups/{group_id}"
    headers = {"Authorization": f"Bearer {ACCESS_KEY}"}
    response = requests.get(url, headers=headers)
    return response.status_code == 200


def _enviar_y_guardar(mensaje: str, group_id: str, url: str, fecha_pub: datetime,
                      proyecto: Proyecto, usuario: Usuario, start_time: datetime, status_list: List[str]) -> bool:
    enviado = enviar_mensaje(mensaje, group_id)
    estado = "Enviado" if enviado else "No Enviado"
    crear_registro_db(url, fecha_pub, estado, mensaje, start_time, enviado, proyecto, usuario)
    status_list.append(estado)
    return enviado


def enviar_mensaje(mensaje: str, grupo_id: str) -> bool:
    if not grupo_id:
        logger.warning("No se proporcionó un grupo_id")
        return False

    url = f"{WHAPI_URL}/messages/text"
    headers = {"Authorization": f"Bearer {ACCESS_KEY}", "Content-Type": "application/json"}
    payload = {"to": grupo_id, "body": mensaje, "no_link_preview": True}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                logger.info("Mensaje enviado correctamente")
                time.sleep(1)
                return True
            logger.error(f"Error al enviar mensaje: {resp.status_code} -> {resp.json()}")
        except requests.RequestException as e:
            logger.error(f"Error de conexión: {e}")
        time.sleep(RETRY_DELAY)
    return False


def _preparar_registro(record: Dict[str, Any], proyecto: Proyecto):
    url_auto = record.get("url") or record.get("URL", "")
    fecha_str = record.get("fechaPublicacion") or record.get("published") or record.get("DATE")
    fecha_e = parse_date(fecha_str)
    formato_f = detect_date_format(fecha_str)

    fecha_publicacion = None
    if fecha_e:
        try:
            fecha_publicacion = (
                fecha_e if isinstance(fecha_e, datetime) else datetime.strptime(fecha_e, formato_f)
            )
        except ValueError:
            fecha_publicacion = datetime.now()

    mensaje = format_message_db(record, proyecto)
    return mensaje, fecha_publicacion, url_auto


def crear_registro_db(link: str, f_pub: Optional[datetime], estado: str, msj: str,
                      fecha_creacion: datetime, enviado: bool, proyect: Proyecto, user: Usuario):
    Datos.objects.create(
        url=link,
        fecha_publicacion=f_pub,
        estado_envio=estado,
        mensaje=msj,
        created_at=fecha_creacion,
        sent_at=datetime.now() if enviado else None,
        proyecto=proyect,
        usuario=user,
        domain=get_platform(link) if link else None,
    )


def get_platform(url: str) -> str:
    platforms = {
        "youtube": ["youtube.com", "youtu.be"],
        "linkedin": ["linkedin.com"],
        "facebook": ["facebook.com"],
        "twitter": ["twitter.com", "x.com"],
        "tiktok": ["tiktok.com"],
        "instagram": ["instagram.com"],
    }
    extracted = tldextract.extract(url)
    for platform, domains in platforms.items():
        if any(domain in url for domain in domains):
            return platform
    dominio = f"{extracted.subdomain}.{extracted.domain}.{extracted.suffix}".strip(".")
    return dominio
