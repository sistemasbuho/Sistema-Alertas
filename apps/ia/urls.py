from django.urls import path

from apps.ia.api.auditoria import EvaluacionDetalleAPIView, EvaluacionesListAPIView
from apps.ia.api.cola_excepciones import (
    ColaExcepcionesListAPIView,
    ColaExcepcionesResumenAPIView,
)
from apps.ia.api.matriz import MatrizClienteAPIView
from apps.ia.api.metricas import MetricasAPIView
from apps.ia.api.resolver_excepcion import (
    ResolverExcepcionAPIView,
    ResolverExcepcionesBulkAPIView,
)

urlpatterns = [
    path("ia/cola-excepciones/", ColaExcepcionesListAPIView.as_view(), name="ia-cola-excepciones"),
    path(
        "ia/cola-excepciones/resumen/",
        ColaExcepcionesResumenAPIView.as_view(),
        name="ia-cola-resumen",
    ),
    path(
        "ia/cola-excepciones/resolver-bulk/",
        ResolverExcepcionesBulkAPIView.as_view(),
        name="ia-cola-resolver-bulk",
    ),
    path(
        "ia/cola-excepciones/<uuid:detalle_id>/resolver/",
        ResolverExcepcionAPIView.as_view(),
        name="ia-cola-resolver",
    ),
    path("ia/matriz/<uuid:proyecto_id>/", MatrizClienteAPIView.as_view(), name="ia-matriz"),
    path("ia/evaluaciones/", EvaluacionesListAPIView.as_view(), name="ia-evaluaciones"),
    path(
        "ia/evaluaciones/<uuid:pk>/",
        EvaluacionDetalleAPIView.as_view(),
        name="ia-evaluacion-detalle",
    ),
    path("ia/metricas/", MetricasAPIView.as_view(), name="ia-metricas"),
]
