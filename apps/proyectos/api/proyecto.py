from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.proyectos.models import Proyecto
from apps.proyectos.serializers.proyecto_serializer import ProyectoCreateSerializer, ProyectoUpdateSerializer
from apps.base.api.filtros import PaginacionEstandar
from apps.proyectos.api.filtros import ProyectoFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.views import APIView
from apps.base.models import DetalleEnvio, Articulo, Redes, TemplateConfig

from typing import Optional
import os
import requests

API_TOKEN = os.getenv("TOKEN_PROYECTO")
WHATSAPP_ACCESS_KEY = os.getenv("WHAPI_TOKEN")


def get_grupo_id(grupo_whatsapp: str) -> Optional[str]:
    url_grupos = "https://gate.whapi.cloud/groups"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_KEY}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(url_grupos, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        for grupo in data.get("groups", []):
            if grupo.get("name") == grupo_whatsapp:
                return grupo.get("id")
    except (requests.RequestException, ValueError, KeyError):
        return None
    return None


class ProyectoAPIView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Proyecto.objects.all()
    serializer_class = ProyectoCreateSerializer
    lookup_field = 'id'
    pagination_class = PaginacionEstandar
    filterset_class = ProyectoFilter
    filter_backends = [DjangoFilterBackend]

    def _validar_token(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return False, "Token no enviado o inválido"
        token = auth_header.split(" ")[1]
        if token != API_TOKEN:
            return False, "Token no autorizado"
        return True, "Token válido"

    def get(self, request, *args, **kwargs):
        proyectos = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(proyectos)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(proyectos, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        serializer = ProyectoCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        grupo_nombre = serializer.validated_data.get("codigo_acceso")
        grupo_id = get_grupo_id(grupo_nombre) if grupo_nombre else None

        if grupo_nombre and not grupo_id:
            return Response(
                {"error": f"No se encontró un grupo de WhatsApp con el nombre '{grupo_nombre}'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        proyecto = serializer.save(
            codigo_acceso=grupo_id if grupo_id else None,
            grupo_nombre=grupo_nombre if grupo_id else None
        )
        return Response(ProyectoCreateSerializer(proyecto).data, status=status.HTTP_201_CREATED)

    def put(self, request, *args, **kwargs):
        proyecto = self.get_object()
        serializer = ProyectoUpdateSerializer(proyecto, data=request.data)
        serializer.is_valid(raise_exception=True)

        if "codigo_acceso" in serializer.validated_data:
            grupo_nombre = serializer.validated_data["codigo_acceso"]
            grupo_id = get_grupo_id(grupo_nombre) if grupo_nombre else None
            if grupo_nombre and not grupo_id:
                return Response(
                    {"error": f"No se encontró un grupo de WhatsApp con el nombre '{grupo_nombre}'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            proyecto = serializer.save(codigo_acceso=grupo_id if grupo_id else proyecto.codigo_acceso)
        else:
            proyecto = serializer.save()

        return Response(ProyectoUpdateSerializer(proyecto).data, status=status.HTTP_200_OK)

    def patch(self, request, *args, **kwargs):
        proyecto = self.get_object()
        serializer = ProyectoUpdateSerializer(proyecto, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        if "codigo_acceso" in serializer.validated_data:
            grupo_nombre = serializer.validated_data["codigo_acceso"]
            grupo_id = get_grupo_id(grupo_nombre) if grupo_nombre else None
            if grupo_nombre and not grupo_id:
                return Response(
                    {"error": f"No se encontró un grupo de WhatsApp con el nombre '{grupo_nombre}'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            proyecto = serializer.save(codigo_acceso=grupo_id if grupo_id else proyecto.codigo_acceso)
        else:
            proyecto = serializer.save()

        return Response(ProyectoUpdateSerializer(proyecto).data, status=status.HTTP_200_OK)



class PlantillaProyectoAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, proyecto_id):
        """
        Retorna la plantilla (config_campos) del proyecto indicado.
        """
        plantilla = {}
        template_config = TemplateConfig.objects.filter(proyecto_id=proyecto_id).first()
        if template_config:
            plantilla = template_config.config_campos

        return Response({"proyecto_id": proyecto_id, "plantilla": plantilla})