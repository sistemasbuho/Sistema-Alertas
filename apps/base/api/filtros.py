import django_filters
from apps.base.models import Redes, Articulo,DetalleEnvio
from rest_framework.pagination import PageNumberPagination



class RedesFilter(django_filters.FilterSet):
    fecha_inicio = django_filters.DateFilter(field_name="fecha", lookup_expr="gte")
    fecha_fin = django_filters.DateFilter(field_name="fecha", lookup_expr="lte")
    autor = django_filters.CharFilter(field_name="autor", lookup_expr="istartswith")
    url = django_filters.CharFilter(field_name="url", lookup_expr="istartswith")
    proyecto = django_filters.CharFilter(field_name="proyecto__nombre", lookup_expr="istartswith")
    estado_enviado = django_filters.BooleanFilter(field_name="detalles_envio__estado_enviado")

    class Meta:
        model = Redes
        fields = ["autor", "url", "proyecto", "fecha_inicio", "fecha_fin", "estado_enviado"]

class MediosFilter(django_filters.FilterSet):
    fecha_inicio = django_filters.DateFilter(field_name="fecha", lookup_expr="gte")
    fecha_fin = django_filters.DateFilter(field_name="fecha", lookup_expr="lte")
    medio = django_filters.CharFilter(field_name="medio", lookup_expr="istartswith")
    ciudad = django_filters.CharFilter(field_name="ciudad", lookup_expr="istartswith")
    proyecto = django_filters.CharFilter(field_name="proyecto__nombre", lookup_expr="istartswith")
    estado_enviado = django_filters.BooleanFilter(field_name="detalles_envio__estado_enviado")


    class Meta:
        model = Articulo
        fields = ["medio", "ciudad", "proyecto", "fecha_inicio", "fecha_fin","estado_enviado"]


class DetalleEnvioFilter(django_filters.FilterSet):
    url = django_filters.CharFilter(field_name="medio__url", lookup_expr="exact")
    url_coincidencia = django_filters.CharFilter(field_name="medio__url", lookup_expr="icontains")
    fecha_creacion_desde = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    fecha_creacion_hasta = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")
    fecha_envio_desde = django_filters.DateTimeFilter(field_name="inicio_envio", lookup_expr="gte")
    fecha_envio_hasta = django_filters.DateTimeFilter(field_name="fin_envio", lookup_expr="lte")

    class Meta:
        model = DetalleEnvio
        fields = [
            "usuario",
            "proyecto",
            "estado_enviado",
            "red_social",
        ]

class PaginacionEstandar(PageNumberPagination):
    page_size = 50  
    page_size_query_param = "page_size"
    max_page_size = 100