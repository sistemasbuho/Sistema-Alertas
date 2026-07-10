from django.db.models import Avg, Count
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ia.models import EvaluacionIA


class MetricasAPIView(APIView):
    """GET /api/ia/metricas/ — evidencia para ajustar umbrales (A4/D4):
    conteos por decisión y tasa de corrección humana por bucket de confianza."""

    def get(self, request):
        queryset = EvaluacionIA.objects.all()
        proyecto = request.query_params.get("proyecto")
        if proyecto:
            queryset = queryset.filter(proyecto_id=proyecto)
        tipo_alerta = request.query_params.get("tipo_alerta")
        if tipo_alerta:
            queryset = queryset.filter(tipo_alerta=tipo_alerta)

        por_decision = list(
            queryset.values("decision").annotate(total=Count("id")).order_by("-total")
        )
        por_decision_por = list(
            queryset.values("decision_por").annotate(total=Count("id")).order_by("-total")
        )
        latencia = queryset.aggregate(avg_ms=Avg("latencia_ms"))["avg_ms"]

        # Buckets de confianza 0.1: cuántas confirmó vs corrigió el humano
        buckets = []
        revisadas = queryset.filter(
            revision_humana__isnull=False, confianza_global__isnull=False
        )
        for i in range(10):
            inferior, superior = i / 10, (i + 1) / 10
            rango = revisadas.filter(
                confianza_global__gte=inferior, confianza_global__lt=superior if i < 9 else 1.01
            )
            total = rango.count()
            if not total:
                continue
            confirmadas = rango.filter(
                revision_humana=EvaluacionIA.REVISION_CONFIRMADA
            ).count()
            buckets.append(
                {
                    "bucket": f"{inferior:.1f}-{superior:.1f}",
                    "total": total,
                    "confirmadas": confirmadas,
                    "corregidas_o_rechazadas": total - confirmadas,
                    "tasa_confirmacion": round(confirmadas / total, 3),
                }
            )

        return Response(
            {
                "total_evaluaciones": queryset.count(),
                "por_decision": por_decision,
                "por_decision_por": por_decision_por,
                "latencia_promedio_ms": latencia,
                "confianza_buckets": buckets,
            }
        )
