from rest_framework import generics
from apps.base.models import Articulo
from apps.base.serializers.serializer_medios import MediosSerializer

class MediosListAPIView(generics.ListAPIView):
    queryset = Articulo.objects.all()
    serializer_class = MediosSerializer

