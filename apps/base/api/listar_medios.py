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
        all_param = self.request.query_params.get("all", "false").lower()

        queryset = (
            Articulo.objects.select_related("proyecto")
            .prefetch_related("detalles_envio")
        )
        if all_param == "true":
            return queryset

        return queryset.filter(detalles_envio__estado_enviado=False).distinct()
    
    def get_serializer_context(self):
        """
        Pasa la plantilla al serializer para que cada registro pueda formatear su mensaje.
        """
        context = super().get_serializer_context()
        proyecto_id = self.request.query_params.get("proyecto_id")
        plantilla_mensaje = {}

        if proyecto_id:
            template_config = TemplateConfig.objects.filter(proyecto=proyecto_id).first()
            if template_config:
                plantilla_mensaje = template_config.config_campos

        context["plantilla"] = plantilla_mensaje
        return context

class MediosUpdateAPIView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Articulo.objects.all()
    serializer_class = MediosSerializer
    lookup_field = "pk"

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

