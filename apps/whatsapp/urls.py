from rest_framework.routers import DefaultRouter
from apps.whatsapp.api.enviar_mensaje import CapturaAlertasMediosAPIView
from django.urls import path

urlpatterns = [
    path('whatsapp/captura_alerta_medios/', CapturaAlertasMediosAPIView.as_view(), name='captura-alerta-medios'),
]