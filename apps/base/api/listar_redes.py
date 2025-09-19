from rest_framework import generics
from apps.base.models import Redes
from django_filters.rest_framework import DjangoFilterBackend
from apps.base.serializers.serializer_redes import RedesSerializer
from apps.base.api.filtros import RedesFilter
from apps.base.api.filtros import PaginacionEstandar
from rest_framework.permissions import IsAuthenticated



def obtener_contenido_twitter(texto, red_social):
    """
    Devuelve el texto hasta QT/Repost (incluyendo la palabra).
    """
    if red_social.lower() == "twitter":
        qt_index = texto.find("QT")
        repost_index = texto.find("Repost")
        indices = [i for i in [qt_index, repost_index] if i != -1]
        if indices:
            corte = min(indices)
            # Agregamos la longitud de la palabra encontrada
            if corte == qt_index:
                corte += len("QT")
            elif corte == repost_index:
                corte += len("Repost")
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
            if not red.red_social:  # saltar si no tiene red social
                continue

            red_social_name = red.red_social.nombre.lower()
            for detalle in red.detalles_envio.all():
                mensaje = detalle.mensaje or ""  # si es None, usar string vacío
                if red_social_name == "twitter":
                    detalle.qt = "Sí" if "QT" in mensaje or "Repost" in mensaje else "No"
                    detalle.mensaje = obtener_contenido_twitter(mensaje, "twitter")
                else:
                    detalle.qt = "No"

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
