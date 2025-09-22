from django.urls import path
from apps.base.api.listar_medios import MediosListAPIView,MediosUpdateAPIView
from apps.base.api.listar_redes import RedesListAPIView,RedesUpdateAPIView

from apps.base.api.importar_medios import ImportarArticuloAPIView
from apps.base.api.importar_redes import ImportarRedesAPIView
from apps.base.api.formato_mensaje import CrearPlantillaAPIView , ListarPlantillasAPIView,CrearCamposPlantillaAPIView
from apps.base.api.historial import HistorialEnviosListAPIView,HistorialEnviosDetailAPIView,ExportarHistorialExcelView
from apps.base.api.ingestion import IngestionAPIView

from apps.base.api.login import (
    UserValidationGoogle,
    EmailTokenObtainPairView,
    EmailTokenRefreshView,
)




urlpatterns = [
    path("auth/google/", UserValidationGoogle.as_view(), name="google-login"),
    path("token/", EmailTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", EmailTokenRefreshView.as_view(), name="token_refresh"),


    path('redes/importar-redes/', ImportarRedesAPIView.as_view(), name='importar-redes'),
    path('redes/', RedesListAPIView.as_view(), name='redes-list'),
    path("redes/<uuid:pk>/", RedesUpdateAPIView.as_view(), name="redes-update"),

    path('medios/importar-articulos/', ImportarArticuloAPIView.as_view(), name='importar-articulo'),
    path('medios/', MediosListAPIView.as_view(), name='medios-list'),
    path("medios/<uuid:pk>/", MediosUpdateAPIView.as_view(), name="update-medio"),
    path("ingestion/", IngestionAPIView.as_view(), name="ingestion"),

    path("plantillas/crear/", CrearPlantillaAPIView.as_view(), name="plantillas-crear"),
    path("plantillas/", ListarPlantillasAPIView.as_view(), name="listar-plantillas"),
    path("plantillas/<uuid:plantilla_id>/campos/", CrearCamposPlantillaAPIView.as_view(), name="crear-campos-plantilla"),

    path("historial-envios/",HistorialEnviosListAPIView.as_view(),name="historial-envios-list"),
    path("historial-envios/<uuid:pk>/",HistorialEnviosDetailAPIView.as_view(),name="historial-envios-detail"),
    path("exportar-historial/", ExportarHistorialExcelView.as_view(), name="exportar-historial"),


]
