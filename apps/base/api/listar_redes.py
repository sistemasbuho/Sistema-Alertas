from rest_framework import generics
from apps.base.models import Redes
from django_filters.rest_framework import DjangoFilterBackend
from apps.base.serializers.serializer_redes import RedesSerializer
from apps.base.api.filtros import RedesFilter
from apps.base.api.filtros import PaginacionEstandar
from rest_framework.permissions import IsAuthenticated



def obtener_contenido_twitter(texto, red_social):
    """
    Devuelve solo la parte del texto antes de QT/Repost si es Twitter.
    """
    if red_social.lower() == "twitter":
        qt_index = texto.find("QT")
        repost_index = texto.find("Repost")
        indices = [i for i in [qt_index, repost_index] if i != -1]
        if indices:
            corte = min(indices)
            return texto[:corte].strip()
        else:
            return texto.strip()
    return texto.strip()


class RedesListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RedesSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = RedesFilter
    pagination_class = PaginacionEstandar

def get_queryset(self):
    all_param = self.request.query_params.get("all", "false").lower()
    queryset = Redes.objects.select_related("proyecto").prefetch_related("detalles_envio")

    if all_param != "true":
        queryset = queryset.filter(detalles_envio__estado_enviado=False).distinct()

    for red in queryset:
        for detalle in red.detalles_envio.all():
            if red.red_social.red_social.lower() == "twitter":
                if "QT" in detalle.mensaje or "Repost" in detalle.mensaje:
                    detalle.qt = "Sí"
                else:
                    detalle.qt = "No"

                detalle.mensaje = obtener_contenido_twitter(detalle.mensaje, "twitter")
            else:
                detalle.qt = "No"  # Otras redes

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
