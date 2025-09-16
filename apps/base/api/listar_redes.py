from rest_framework import generics
from apps.base.models import Redes
from django_filters.rest_framework import DjangoFilterBackend
from apps.base.serializers.serializer_redes import RedesSerializer
from apps.base.api.filtros import RedesFilter
from apps.base.api.filtros import PaginacionEstandar
from rest_framework.permissions import IsAuthenticated


class RedesListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RedesSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = RedesFilter
    pagination_class = PaginacionEstandar

    def get_queryset(self):

        all_param = self.request.query_params.get("all", "false").lower()
        queryset = (
            Redes.objects.select_related("proyecto")
            .prefetch_related("detalles_envio")
        )

        if all_param == "true":
            return queryset

        return queryset.filter(detalles_envio__estado_enviado=False).distinct()

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
