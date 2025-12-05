from rest_framework import generics
from django_filters.rest_framework import DjangoFilterBackend
from apps.base.models import Articulo
from apps.base.serializers.serializer_medios import MediosSerializer
from apps.base.api.filtros import MediosFilter
from apps.base.api.filtros import PaginacionEstandar
from rest_framework.permissions import IsAuthenticated

class MediosListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MediosSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = MediosFilter
    pagination_class = PaginacionEstandar

    def get_queryset(self):

        queryset = (
            Articulo.objects.select_related("proyecto")
            .prefetch_related("detalles_envio")
            .filter(proyecto__tipo_alerta='medios')
        )


        return queryset
    


class MediosUpdateAPIView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Articulo.objects.all()
    serializer_class = MediosSerializer
    lookup_field = "pk"

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

