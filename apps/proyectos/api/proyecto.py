from rest_framework import generics
from apps.proyectos.models import Proyecto
from apps.proyectos.serializers.proyecto_serializer  import ProyectoCreateSerializer,ProyectoUpdateSerializer
from rest_framework.response import Response
from rest_framework import generics, status
from apps.base.api.filtros import PaginacionEstandar
from apps.proyectos.api.filtros import ProyectoFilter


class ProyectoAPIView(generics.GenericAPIView):
    queryset = Proyecto.objects.all()
    serializer_class = ProyectoCreateSerializer
    lookup_field = 'id'
    pagination_class = PaginacionEstandar
    filterset_class = ProyectoFilter

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