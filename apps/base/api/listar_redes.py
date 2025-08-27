from rest_framework import generics
from apps.base.models import Redes
from apps.base.serializers.serializer_redes import RedesSerializer

class RedesListAPIView(generics.ListAPIView):
    queryset = Redes.objects.all()
    serializer_class = RedesSerializer
