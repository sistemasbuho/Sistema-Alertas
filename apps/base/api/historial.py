from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from apps.base.models import DetalleEnvio
from apps.base.serializers.serializer_historial import DetalleEnvioSerializer
from apps.base.api.filtros import DetalleEnvioFilter
from rest_framework import generics
from apps.base.api.filtros import PaginacionEstandar


class HistorialEnviosListAPIView(generics.ListAPIView):
    """
    Lista de historial de envíos con filtros.
    """
    serializer_class = DetalleEnvioSerializer
    queryset = DetalleEnvio.objects.select_related("usuario", "proyecto", "red_social")

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = {
        "usuario": ["exact"],
        "proyecto": ["exact"],
        "estado_enviado": ["exact"],
        "created_at": ["gte", "lte"],       # filtros desde/hasta
        "inicio_envio": ["gte", "lte"],     # filtros desde/hasta
        "fin_envio": ["gte", "lte"],        # filtros desde/hasta
        "medio__url": ["exact", "icontains"],
        "red_social__red_social__nombre": ["icontains"],
    }
    search_fields = ["mensaje", "medio__url", "red_social__url"]

    pagination_class = PaginacionEstandar

class HistorialEnviosDetailAPIView(generics.RetrieveAPIView):
    """
    Detalle de un registro de envío.
    """
    serializer_class = DetalleEnvioSerializer
    queryset = DetalleEnvio.objects.select_related("usuario", "proyecto", "red_social")
    lookup_field = "pk"