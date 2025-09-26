from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse
from django.utils.encoding import escape_uri_path
from django.views import View
import openpyxl
from rest_framework import filters, generics, viewsets
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated

from apps.base.api.filtros import DetalleEnvioFilter, PaginacionEstandar
from apps.base.models import DetalleEnvio
from apps.base.serializers.serializer_historial import DetalleEnvioSerializer




class HistorialEnviosListAPIView(generics.ListAPIView):
    """
    Lista de historial de envíos con filtros usando django_filters.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DetalleEnvioSerializer
    queryset = DetalleEnvio.objects.select_related("usuario", "proyecto", "red_social")

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = DetalleEnvioFilter
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
        usuario_nombre = request.GET.get("usuario_nombre")
        proyecto = request.GET.get("proyecto")
        proyecto_nombre = request.GET.get("proyecto_nombre")
        estado = request.GET.get("estado_enviado")
        created_at_desde = request.GET.get("created_at_desde")
        created_at_hasta = request.GET.get("created_at_hasta")
        inicio_envio_desde = request.GET.get("inicio_envio_desde")
        fin_envio_hasta = request.GET.get("fin_envio_hasta")
        medio_url = request.GET.get("medio_url")
        medio_url_coincide = request.GET.get("medio_url_coincide")
        red_social_nombre = request.GET.get("red_social_nombre")
        search = request.GET.get("search")

        queryset = DetalleEnvio.objects.select_related(
            "usuario", "proyecto", "medio", "red_social__red_social"
        )

        # Filtros
        if usuario:
            queryset = queryset.filter(usuario_id=usuario)
        if usuario_nombre:
            queryset = queryset.filter(usuario__username__icontains=usuario_nombre)
        if proyecto:
            queryset = queryset.filter(proyecto_id=proyecto)
        if proyecto_nombre:
            queryset = queryset.filter(proyecto__nombre__icontains=proyecto_nombre)
        if isinstance(estado, str):
            estado_normalizado = estado.strip().lower()
            valores_verdaderos = {"true", "1", "si", "sí", "enviado"}
            valores_falsos = {"false", "0", "no", "pendiente", "no_enviado", "no enviado"}
            if estado_normalizado in valores_verdaderos:
                queryset = queryset.filter(estado_enviado=True)
            elif estado_normalizado in valores_falsos:
                queryset = queryset.filter(estado_enviado=False)
        if created_at_desde:
            queryset = queryset.filter(created_at__gte=created_at_desde)
        if created_at_hasta:
            queryset = queryset.filter(created_at__lte=created_at_hasta)
        if inicio_envio_desde:
            queryset = queryset.filter(inicio_envio__gte=inicio_envio_desde)
        if fin_envio_hasta:
            queryset = queryset.filter(fin_envio__lte=fin_envio_hasta)
        if medio_url:
            queryset = queryset.filter(medio__url=medio_url)
        if medio_url_coincide:
            queryset = queryset.filter(medio__url__icontains=medio_url_coincide)
        if red_social_nombre:
            queryset = queryset.filter(
                red_social__red_social__nombre__icontains=red_social_nombre
            )
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
