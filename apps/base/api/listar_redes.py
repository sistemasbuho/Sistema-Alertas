from rest_framework import generics
from apps.base.models import Redes
from django_filters.rest_framework import DjangoFilterBackend
from apps.base.serializers.serializer_redes import RedesSerializer
from apps.base.api.filtros import RedesFilter
from apps.base.api.filtros import PaginacionEstandar
from rest_framework.permissions import IsAuthenticated
from django.db.models import Prefetch
from apps.base.models import DetalleEnvio


class RedesListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RedesSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = RedesFilter
    pagination_class = PaginacionEstandar

    def get_queryset(self):
        queryset = Redes.objects.select_related(
            "proyecto",
            "red_social"
        ).prefetch_related(
            Prefetch(
                "detalles_envio",
                queryset=DetalleEnvio.objects.select_related("usuario")
            )
        ).filter(proyecto__tipo_alerta='redes')

        return queryset

class RedesUpdateAPIView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Redes.objects.all()
    serializer_class = RedesSerializer
    lookup_field = "pk"  # usa la PK (UUID o ID) para identificar el objeto

    def perform_update(self, serializer):
        """
        Sobrescribe el update para guardar el usuario que actualiza.
        """
        serializer.save(updated_by=self.request.user)
