from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.base.api.filtros import PaginacionEstandar
from apps.ia.models import EvaluacionIA
from apps.ia.serializers.serializer_evaluacion import (
    EvaluacionIADetalleSerializer,
    EvaluacionIAResumenSerializer,
)


class EvaluacionesListAPIView(APIView):
    """GET /api/ia/evaluaciones/ — log de auditoría D5, filtrable."""

    def get(self, request):
        queryset = EvaluacionIA.objects.select_related(
            "proyecto", "detalle_envio"
        ).order_by("-created_at")

        filtros_directos = {
            "proyecto": "proyecto_id",
            "decision": "decision",
            "decision_por": "decision_por",
            "revision_humana": "revision_humana",
            "tipo_alerta": "tipo_alerta",
            "tonalidad": "tonalidad",
            "detalle_envio": "detalle_envio_id",
        }
        for parametro, campo in filtros_directos.items():
            valor = request.query_params.get(parametro)
            if valor:
                queryset = queryset.filter(**{campo: valor})

        fecha_desde = request.query_params.get("fecha_desde")
        if fecha_desde:
            queryset = queryset.filter(created_at__date__gte=fecha_desde)
        fecha_hasta = request.query_params.get("fecha_hasta")
        if fecha_hasta:
            queryset = queryset.filter(created_at__date__lte=fecha_hasta)

        paginador = PaginacionEstandar()
        pagina = paginador.paginate_queryset(queryset, request)
        serializer = EvaluacionIAResumenSerializer(pagina, many=True)
        return paginador.get_paginated_response(serializer.data)


class EvaluacionDetalleAPIView(APIView):
    """GET /api/ia/evaluaciones/<id>/ — '¿por qué la IA decidió esto?'"""

    def get(self, request, pk):
        evaluacion = get_object_or_404(
            EvaluacionIA.objects.select_related("proyecto", "detalle_envio", "revisado_por"),
            id=pk,
        )
        return Response(EvaluacionIADetalleSerializer(evaluacion).data)
