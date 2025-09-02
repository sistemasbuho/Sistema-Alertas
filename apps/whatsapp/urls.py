from django.urls import path
from apps.whatsapp.api.enviar_mensaje import CapturaAlertasViewSet


urlpatterns = [
    path("whatsapp/captura_alerta_medios", capturar_alertas_medios.as_view(), name="captura-alerta-medios"),
]
