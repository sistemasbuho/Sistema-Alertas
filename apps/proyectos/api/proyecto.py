from rest_framework import generics
from apps.proyectos.models import Proyecto
from apps.proyectos.serializers.proyecto_serializer  import ProyectoCreateSerializer,ProyectoUpdateSerializer
from rest_framework.response import Response
from rest_framework import generics, status
from apps.base.api.filtros import PaginacionEstandar
from apps.proyectos.api.filtros import ProyectoFilter
from django_filters.rest_framework import DjangoFilterBackend
import os


API_TOKEN = os.getenv("TOKEN_PROYECTO")

class ProyectoAPIView(generics.GenericAPIView):
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

        if token != settings.API_TOKEN:
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
    
    # Método para crear un proyecto
    def post(self, request, *args, **kwargs):
        serializer = ProyectoCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # Método para actualizar un proyecto existente
    def put(self, request, *args, **kwargs):
        proyecto = self.get_object()
        serializer = ProyectoUpdateSerializer(proyecto, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    # Método para actualización parcial (PATCH)
    def patch(self, request, *args, **kwargs):
        proyecto = self.get_object()
        serializer = ProyectoUpdateSerializer(proyecto, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)