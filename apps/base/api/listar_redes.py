from rest_framework import generics
from apps.base.models import Redes
from django_filters.rest_framework import DjangoFilterBackend
from apps.base.serializers.serializer_redes import RedesSerializer
from apps.base.api.filtros import RedesFilter


class RedesListAPIView(generics.ListAPIView):
    queryset = Redes.objects.all()
    serializer_class = RedesSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = RedesFilter
