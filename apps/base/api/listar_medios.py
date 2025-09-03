from rest_framework import generics
from django_filters.rest_framework import DjangoFilterBackend
from apps.base.models import Articulo
from apps.base.serializers.serializer_medios import MediosSerializer
from apps.base.api.filtros import MediosFilter

class MediosListAPIView(generics.ListAPIView):
    queryset = Articulo.objects.all()
    serializer_class = MediosSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = MediosFilter


class MediosUpdateAPIView(generics.UpdateAPIView):
    queryset = Articulo.objects.all()
    serializer_class = MediosSerializer
    lookup_field = "pk"

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

