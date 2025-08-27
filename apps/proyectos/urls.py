from django.urls import path
from apps.proyectos.api.proyecto import ProyectoAPIView

urlpatterns = [
    path("proyectos/", ProyectoAPIView.as_view(), name="proyectos-list"),
    path('proyectos/crear/', ProyectoAPIView.as_view(), name='proyecto-crear'),
    path('proyectos/<uuid:id>/', ProyectoAPIView.as_view(), name='proyecto-editar'),
]