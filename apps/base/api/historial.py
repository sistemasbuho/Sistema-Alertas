from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse
from django.utils import timezone
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
        tipo = request.GET.get("tipo")
        search = request.GET.get("search")

        queryset_base = DetalleEnvio.objects.select_related(
            "usuario", "proyecto", "medio", "red_social__red_social"
        )
        queryset = queryset_base

        # Filtros
        if tipo:
            tipo_normalizado = tipo.strip().lower()
            if tipo_normalizado in ["medios", "medio"]:
                queryset = queryset.filter(medio__isnull=False)
            elif tipo_normalizado in ["redes", "red", "red_social"]:
                queryset = queryset.filter(red_social__isnull=False)

        # Aplicar filtros comunes del FilterSet (mismos que el listado)
        filtro = DetalleEnvioFilter(request.GET, queryset=queryset)
        queryset = filtro.qs

        # Filtros adicionales no cubiertos por el FilterSet
        if usuario:
            queryset = queryset.filter(usuario_id=usuario)
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

        # Determinar si la descarga es exclusivamente de redes
        es_solo_redes = False
        if tipo:
            tipo_normalizado = tipo.strip().lower()
            if tipo_normalizado in ["redes", "red", "red_social"]:
                es_solo_redes = True

        # Encabezados dinámicos según el tipo
        if es_solo_redes:
            encabezados = [
                "Proyecto", "Usuario", "Tipo", "Medio/Red", "Tipo de Medio", "URL", "Fecha Publicación",
                "Estado de Envío", "Mensaje Enviado", "Titular",
                "Contenido", "Autor", "Reach", "Engagement", "Ubicación", "Creado En",
                "Fecha de Envío", "Tiempo de Envío"
            ]
        else:
            encabezados = [
                "Proyecto", "Usuario", "Tipo", "Medio/Red", "Tipo de Medio", "URL", "Fecha Publicación",
                "Estado de Envío", "Mensaje Enviado", "Titular",
                "Contenido", "Autor", "Reach", "Engagement", "Ubicación", "Creado En",
                "Fecha de Envío", "Tiempo de Envío"
            ]

        ws.append(encabezados)

        for envio in queryset:
            medio = envio.medio
            red = envio.red_social

            # Calcular tiempo de envío
            tiempo_envio = ""
            if envio.inicio_envio and envio.fin_envio:
                tiempo_envio = str(envio.fin_envio - envio.inicio_envio)

            # Extraer dominio de URL
            def extraer_dominio(url):
                if not url:
                    return ""
                from urllib.parse import urlparse
                parsed = urlparse(url)
                return parsed.netloc or ""

            def _dt_to_str(value):
                """
                Devuelve la fecha en la zona horaria del proyecto (config actual).
                """
                if not value:
                    return ""
                value_local = timezone.localtime(value)
                return value_local.strftime("%Y-%m-%d %H:%M:%S")

            # Determinar tipo y medio/red
            if medio:
                tipo = "Medios"
                medio_red = medio.fuente or ""
                fuente = ""
                tipo_medio_valor = medio.tipo_medio or ""
                url = medio.url
                fecha_pub = _dt_to_str(medio.fecha_publicacion)
                titular = medio.titulo or ""
                contenido = medio.contenido or ""
                autor = medio.autor or ""
                reach = medio.reach if medio.reach is not None else ""
                engagement = medio.engagement if medio.engagement is not None else ""
                ubicacion = medio.ubicacion or ""
                usuario_creador = medio.created_by
            elif red:
                tipo = "Redes"
                red_social_nombre = red.red_social.nombre if red.red_social else ""
                if red_social_nombre and red_social_nombre.lower() == "twitter":
                    red_social_nombre = "X"
                medio_red = red_social_nombre
                fuente = ""
                tipo_medio_valor = red_social_nombre
                url = red.url
                fecha_pub = _dt_to_str(red.fecha_publicacion)
                titular = ""
                contenido = red.contenido or ""
                autor = red.autor or ""
                reach = red.reach if red.reach is not None else ""
                engagement = red.engagement if red.engagement is not None else ""
                ubicacion = red.ubicacion or ""
                usuario_creador = red.created_by
            else:
                tipo = ""
                medio_red = ""
                fuente = ""
                tipo_medio_valor = ""
                url = ""
                fecha_pub = ""
                titular = ""
                contenido = ""
                autor = ""
                reach = ""
                engagement = ""
                ubicacion = ""
                usuario_creador = None

            # Determinar qué usuario mostrar
            if envio.estado_enviado:
                # Si se envió, mostrar el usuario que envió
                usuario_mostrar = envio.usuario.username if envio.usuario else ""
            else:
                # Si no se ha enviado, mostrar el usuario que creó la alerta
                usuario_mostrar = usuario_creador.username if usuario_creador else ""

            # Construir fila según el tipo de descarga
            if es_solo_redes:
                fila = [
                    envio.proyecto.nombre if envio.proyecto else "",
                    usuario_mostrar,
                    tipo,
                    medio_red,
                    tipo_medio_valor,
                    url,
                    fecha_pub,
                    "Sí" if envio.estado_enviado else "No",
                    envio.mensaje or "",
                    titular,
                    contenido,
                    autor,
                    reach,
                    engagement,
                    ubicacion,
                    _dt_to_str(envio.created_at),
                    _dt_to_str(envio.inicio_envio),
                    tiempo_envio,
                ]
            else:
                fila = [
                    envio.proyecto.nombre if envio.proyecto else "",
                    usuario_mostrar,
                    tipo,
                    medio_red,
                    tipo_medio_valor,
                    url,
                    fecha_pub,
                    "Sí" if envio.estado_enviado else "No",
                    envio.mensaje or "",
                    titular,
                    contenido,
                    autor,
                    reach,
                    engagement,
                    ubicacion,
                    _dt_to_str(envio.created_at),
                    _dt_to_str(envio.inicio_envio),
                    tiempo_envio,
                ]

            ws.append(fila)

        # Respuesta
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            "attachment; filename=%s" % escape_uri_path("historial_envios.xlsx")
        )
        wb.save(response)
        return response
