from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from apps.ia.models import EnriquecimientoLog, EvaluacionIA, MatrizCliente


@admin.register(MatrizCliente)
class MatrizClienteAdmin(SimpleHistoryAdmin):
    list_display = ("proyecto", "activo", "modo", "incluir_bandera", "incluir_semaforo", "modified_at")
    list_filter = ("activo", "modo")
    search_fields = ("proyecto__nombre",)


@admin.register(EvaluacionIA)
class EvaluacionIAAdmin(SimpleHistoryAdmin):
    list_display = (
        "id",
        "proyecto",
        "tipo_alerta",
        "estado",
        "decision",
        "decision_por",
        "tonalidad",
        "confianza_global",
        "revision_humana",
        "created_at",
    )
    list_filter = ("estado", "decision", "decision_por", "tipo_alerta", "revision_humana")
    search_fields = ("proyecto__nombre", "detalle_envio__id")
    readonly_fields = [f.name for f in EvaluacionIA._meta.fields]


@admin.register(EnriquecimientoLog)
class EnriquecimientoLogAdmin(admin.ModelAdmin):
    list_display = ("detalle_envio", "campo", "fuente", "exito", "latencia_ms", "created_at")
    list_filter = ("fuente", "exito", "campo")
