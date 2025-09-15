from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from apps.base.models import DetalleEnvio
from apps.base.serializers.serializer_historial import DetalleEnvioSerializer
from apps.base.api.filtros import DetalleEnvioFilter
from rest_framework import generics
from apps.base.api.filtros import PaginacionEstandar
from django.views import View
import openpyxl
from openpyxl.utils import get_column_letter
from django.http import HttpResponse
from rest_framework.filters import SearchFilter
from django.utils.encoding import escape_uri_path
from rest_framework.permissions import IsAuthenticated





class HistorialEnviosListAPIView(generics.ListAPIView):
    """
    Lista de historial de envíos con filtros.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DetalleEnvioSerializer
    queryset = DetalleEnvio.objects.select_related("usuario", "proyecto", "red_social")

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = {
        "usuario": ["exact"],
        "proyecto": ["exact"],
        "estado_enviado": ["exact"],
        "created_at": ["gte", "lte"],       
        "inicio_envio": ["gte", "lte"],     
        "fin_envio": ["gte", "lte"],       
        "medio__url": ["exact", "icontains"],
        "red_social__red_social__nombre": ["icontains"],
    }
    search_fields = ["mensaje", "medio__url", "red_social__url"]

    pagination_class = PaginacionEstandar

class HistorialEnviosDetailAPIView(generics.RetrieveAPIView):
    """
    Detalle de un registro de envío.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DetalleEnvioSerializer
    queryset = DetalleEnvio.objects.select_related("usuario", "proyecto", "red_social")
    lookup_field = "pk"


class ExportarHistorialExcelView(View):
    def get(self, request, *args, **kwargs):
        usuario = request.GET.get("usuario")
        proyecto = request.GET.get("proyecto")
        estado = request.GET.get("estado_enviado")
        fecha_inicio = request.GET.get("created_at__gte")
        fecha_fin = request.GET.get("created_at__lte")
        search = request.GET.get("search")

        queryset = DetalleEnvio.objects.select_related(
            "usuario", "proyecto", "medio", "red_social__red_social"
        )

        # Filtros
        if usuario:
            queryset = queryset.filter(usuario_id=usuario)
        if proyecto:
            queryset = queryset.filter(proyecto_id=proyecto)
        if estado is not None:
            queryset = queryset.filter(estado_enviado=estado.lower() == "true")
        if fecha_inicio:
            queryset = queryset.filter(created_at__gte=fecha_inicio)
        if fecha_fin:
            queryset = queryset.filter(created_at__lte=fecha_fin)
        if search:
            queryset = queryset.filter(
                Q(mensaje__icontains=search)
                | Q(medio__titulo__icontains=search)
                | Q(medio__contenido__icontains=search)
                | Q(red_social__contenido__icontains=search)
            )

        # Crear Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Historial Envíos"

        # Encabezados
        ws.append([
            "Proyecto", "Usuario", "URL", "Red", "Fecha Publicación",
            "Estado de Envío", "Mensaje Original", "Autor", "Reach",
            "Engagement", "Fecha Publicacion Mensaje", "Contenido",
            "URL Mensaje", "Titular", "Creado En", "Fecha de Envío",
            "Tiempo de Envío"
        ])

        for envio in queryset:
            medio = envio.medio
            red = envio.red_social

            # Calcular tiempo de envío
            tiempo_envio = ""
            if envio.inicio_envio and envio.fin_envio:
                tiempo_envio = str(envio.fin_envio - envio.inicio_envio)

            ws.append([
                envio.proyecto.nombre if envio.proyecto else "",
                envio.usuario.username if envio.usuario else "",
                medio.url if medio else (red.url if red else ""),
                red.red_social.nombre if red and red.red_social else "",
                medio.fecha_publicacion.strftime("%Y-%m-%d %H:%M:%S") if medio and medio.fecha_publicacion else (
                    red.fecha_publicacion.strftime("%Y-%m-%d %H:%M:%S") if red and red.fecha_publicacion else ""
                ),
                "Sí" if envio.estado_enviado else "No",
                envio.mensaje or "",
                medio.autor if medio else (red.autor if red else ""),
                medio.reach if medio else (red.reach if red else ""),
                red.engagement if red else "",
                red.fecha_publicacion.strftime("%Y-%m-%d %H:%M:%S") if red and red.fecha_publicacion else "",
                red.contenido if red else "",
                red.url if red else "",
                medio.titulo if medio else "",
                envio.created_at.strftime("%Y-%m-%d %H:%M:%S") if envio.created_at else "",
                envio.inicio_envio.strftime("%Y-%m-%d %H:%M:%S") if envio.inicio_envio else "",
                tiempo_envio,
            ])

        # Respuesta
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            "attachment; filename=%s" % escape_uri_path("historial_envios.xlsx")
        )
        wb.save(response)
        return response