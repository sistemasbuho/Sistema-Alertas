from rest_framework.routers import DefaultRouter
from apps.whatsapp.api.enviar_mensaje import CapturaAlertasMediosAPIView,CapturaAlertasRedesAPIView,EnviarMensajeAPIView
from django.urls import path

urlpatterns = [
    path('whatsapp/captura_alerta_medios/', CapturaAlertasMediosAPIView.as_view(), name='captura-alerta-medios'),
    path('whatsapp/captura_alerta_redes/', CapturaAlertasRedesAPIView.as_view(), name='captura-alerta-redes'),
    path('whatsapp/envio_alerta/', EnviarMensajeAPIView.as_view(), name='enviar-alerta'),

]