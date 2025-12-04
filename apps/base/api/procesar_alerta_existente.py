from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.base.models import Articulo, Redes, DetalleEnvio
from apps.proyectos.models import Proyecto
from apps.base.api.utils import formatear_fecha_respuesta


class ProcesarAlertaExistenteAPIView(APIView):
    """
    Procesa una alerta existente (medio o red) que ya fue creada
    pero no fue enviada, creando o actualizando su DetalleEnvio.

    Casos de uso:
    - Alerta que fue rechazada por filtros pero ahora se quiere enviar
    - Alerta que se ingresó sin envío automático
    - Alerta que falló en el envío y se quiere reintentar
    """

    def post(self, request):
        proyecto_id = request.data.get("proyecto_id")
        tipo = request.data.get("tipo")  # "medio" o "red"
        alerta_id = request.data.get("alerta_id")

        # Validaciones
        if not proyecto_id:
            return Response(
                {"error": "Se requiere 'proyecto_id'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not tipo or tipo not in ["medio", "red"]:
            return Response(
                {"error": "El campo 'tipo' debe ser 'medio' o 'red'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not alerta_id:
            return Response(
                {"error": "Se requiere 'alerta_id'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validar proyecto
        proyecto = get_object_or_404(Proyecto, id=proyecto_id)

        # Obtener la alerta según el tipo
        if tipo == "medio":
            alerta = get_object_or_404(Articulo, id=alerta_id)
            # Validar que la alerta pertenece al proyecto
            if alerta.proyecto_id != proyecto.id:
                return Response(
                    {"error": "El medio no pertenece al proyecto especificado"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:  # tipo == "red"
            alerta = get_object_or_404(Redes, id=alerta_id)
            # Validar que la alerta pertenece al proyecto
            if alerta.proyecto_id != proyecto.id:
                return Response(
                    {"error": "La red social no pertenece al proyecto especificado"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Crear o actualizar DetalleEnvio
        filtros = {"proyecto_id": proyecto_id}
        if tipo == "medio":
            filtros["medio_id"] = alerta_id
        else:
            filtros["red_social_id"] = alerta_id

        detalle_envio, created = DetalleEnvio.objects.get_or_create(
            **filtros,
            defaults={
                "estado_enviado": False,
                "estado_revisado": False,
                "usuario": request.user if request.user.is_authenticated else None,
            },
        )

        # Si ya existía y ya fue enviado, informar
        if not created and detalle_envio.estado_enviado:
            # Formato compatible con ingesta
            alerta_data = self._construir_alerta_respuesta(alerta, tipo)
            return Response(
                {
                    "proveedor": "procesamiento_manual",
                    "mensaje": "0 registros creados (1 duplicados)",
                    "listado": [],
                    "errores": [],
                    "duplicados": 1,
                    "descartados": 0,
                    "proyecto_keywords": proyecto.keywords or [],
                    "proyecto_nombre": proyecto.nombre,
                    "info_adicional": {
                        "alerta_ya_enviada": True,
                        "fecha_envio": detalle_envio.fin_envio,
                        "detalle_envio_id": str(detalle_envio.id),
                    },
                },
                status=status.HTTP_200_OK,
            )

        # Si no estaba enviado, resetear estados para permitir reenvío
        if not created:
            detalle_envio.estado_enviado = False
            detalle_envio.estado_revisado = False
            detalle_envio.inicio_envio = None
            detalle_envio.fin_envio = None
            detalle_envio.save()

        # Construir respuesta en formato compatible con ingesta
        alerta_data = self._construir_alerta_respuesta(alerta, tipo)

        return Response(
            {
                "proveedor": "procesamiento_manual",
                "mensaje": "1 registros creados",
                "listado": [alerta_data],
                "errores": [],
                "duplicados": 0,
                "descartados": 0,
                "proyecto_keywords": proyecto.keywords or [],
                "proyecto_nombre": proyecto.nombre,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def _construir_alerta_respuesta(self, alerta, tipo):
        """Construye la estructura de alerta compatible con el formato de ingesta"""
        if tipo == "medio":
            return {
                "id": str(alerta.id),
                "url": alerta.url,
                "titulo": alerta.titulo or "",
                "contenido": alerta.contenido or "",
                "autor": alerta.autor or "",
                "fecha": formatear_fecha_respuesta(alerta.fecha_publicacion),
                "fecha_publicacion": formatear_fecha_respuesta(alerta.fecha_publicacion),
                "reach": alerta.reach,
                "tipo": "medio",
            }
        else:  # red
            return {
                "id": str(alerta.id),
                "url": alerta.url,
                "contenido": alerta.contenido or "",
                "autor": alerta.autor or "",
                "fecha": formatear_fecha_respuesta(alerta.fecha_publicacion),
                "fecha_publicacion": formatear_fecha_respuesta(alerta.fecha_publicacion),
                "reach": alerta.reach,
                "engagement": alerta.engagement,
                "red_social": alerta.red_social.nombre if alerta.red_social else "",
                "tipo": "red",
            }
