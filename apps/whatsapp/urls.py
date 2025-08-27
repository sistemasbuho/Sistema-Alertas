from django.urls import path
from apps.whatsapp.api.enviar_mensaje import CapturaAlertasViewSet


urlpatterns = [
    path("whatsapp/captura_alerta", CapturaAlertasViewSet.as_view(), name="captura-alerta"),
]
