from django.db.models import Count
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.base.api.filtros import PaginacionEstandar
from apps.base.models import DetalleEnvio
from apps.ia.serializers.serializer_cola import AlertaExcepcionSerializer


def _queryset_cola():
    return (
        DetalleEnvio.objects.filter(
            estado_pipeline=DetalleEnvio.PIPELINE_COLA_EXCEPCIONES
        )
        .select_related("proyecto", "red_social__red_social", "medio")
        .prefetch_related("evaluaciones_ia")
        .order_by("-created_at")
    )


class ColaExcepcionesListAPIView(APIView):
    """GET /api/ia/cola-excepciones/ — alertas dudosas con sugerencias IA."""

    def get(self, request):
        queryset = _queryset_cola()

        proyecto = request.query_params.get("proyecto")
        if proyecto:
            queryset = queryset.filter(proyecto_id=proyecto)

        tipo = request.query_params.get("tipo")
        if tipo == "redes":
            queryset = queryset.filter(red_social__isnull=False)
        elif tipo == "medios":
            queryset = queryset.filter(medio__isnull=False)

        # Filtros sobre la última evaluación (aproximación: cualquier evaluación
        # del detalle; en la práctica hay una vigente)
        tonalidad = request.query_params.get("tonalidad")
        if tonalidad:
            queryset = queryset.filter(evaluaciones_ia__tonalidad=tonalidad)

        decision_por = request.query_params.get("decision_por")
        if decision_por:
            queryset = queryset.filter(evaluaciones_ia__decision_por=decision_por)

        confianza_max = request.query_params.get("confianza_max")
        if confianza_max:
            queryset = queryset.filter(
                evaluaciones_ia__confianza_global__lte=float(confianza_max)
            )
        confianza_min = request.query_params.get("confianza_min")
        if confianza_min:
            queryset = queryset.filter(
                evaluaciones_ia__confianza_global__gte=float(confianza_min)
            )

        queryset = queryset.distinct()

        paginador = PaginacionEstandar()
        pagina = paginador.paginate_queryset(queryset, request)
        serializer = AlertaExcepcionSerializer(pagina, many=True)
        return paginador.get_paginated_response(serializer.data)


class ColaExcepcionesResumenAPIView(APIView):
    """GET /api/ia/cola-excepciones/resumen/ — contador para el badge."""

    def get(self, request):
        queryset = _queryset_cola()
        por_proyecto = (
            queryset.values("proyecto_id", "proyecto__nombre")
            .annotate(pendientes=Count("id"))
            .order_by("-pendientes")
        )
        return Response(
            {
                "pendientes": queryset.count(),
                "por_proyecto": [
                    {
                        "proyecto": str(p["proyecto_id"]),
                        "proyecto_nombre": p["proyecto__nombre"],
                        "pendientes": p["pendientes"],
                    }
                    for p in por_proyecto
                ],
            }
        )
