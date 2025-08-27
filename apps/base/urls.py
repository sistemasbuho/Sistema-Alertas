from django.urls import path
from apps.base.api.login import GoogleLoginAPIView
from apps.base.api.listar_medios import MediosListAPIView
from apps.base.api.listar_redes import RedesListAPIView

from apps.base.api.importar_medios import ImportarArticuloAPIView
from apps.base.api.importar_redes import ImportarRedesAPIView




urlpatterns = [
    path("auth/google/", GoogleLoginAPIView.as_view(), name="google-login"),
    path('medios/importar-articulos/', ImportarArticuloAPIView.as_view(), name='importar-articulo'),
    path('redes/importar-redes/', ImportarRedesAPIView.as_view(), name='importar-redes'),
    path('redes/', RedesListAPIView.as_view(), name='redes-list'),
    path('medios/', MediosListAPIView.as_view(), name='medios-list'),
]
