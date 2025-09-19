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
    url = django_filters.CharFilter(field_name="url", lookup_expr="istartswith")
    autor = django_filters.CharFilter(field_name="autor", lookup_expr="istartswith")

    ciudad = django_filters.CharFilter(field_name="ciudad", lookup_expr="istartswith")
    proyecto = django_filters.CharFilter(field_name="proyecto__nombre", lookup_expr="istartswith")
    estado_enviado = django_filters.BooleanFilter(field_name="detalles_envio__estado_enviado")


    class Meta:
        model = Articulo
        fields = ["medio", "url","ciudad", "proyecto", "fecha_inicio", "fecha_fin","estado_enviado","autor"]


class DetalleEnvioFilter(django_filters.FilterSet):
    usuario_nombre = django_filters.CharFilter(field_name="usuario__username", lookup_expr="icontains")
    proyecto_nombre = django_filters.CharFilter(field_name="proyecto__nombre", lookup_expr="icontains")
    estado_enviado = django_filters.BooleanFilter(field_name="estado_enviado")
    created_at_desde = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_hasta = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")
    inicio_envio_desde = django_filters.DateTimeFilter(field_name="inicio_envio", lookup_expr="gte")
    fin_envio_hasta = django_filters.DateTimeFilter(field_name="fin_envio", lookup_expr="lte")
    medio_url = django_filters.CharFilter(field_name="medio__url", lookup_expr="exact")
    medio_url_coincide = django_filters.CharFilter(field_name="medio__url", lookup_expr="icontains")
    red_social_nombre = django_filters.CharFilter(field_name="red_social__red_social__nombre", lookup_expr="icontains")

    class Meta:
        model = DetalleEnvio
        fields = [
            "usuario_nombre",
            "proyecto_nombre",
            "estado_enviado",
            "created_at_desde",
            "created_at_hasta",
            "inicio_envio_desde",
            "fin_envio_hasta",
            "medio_url",
            "medio_url_coincide",
            "red_social_nombre",
        ]


class PaginacionEstandar(PageNumberPagination):
    page_size = 50  
    page_size_query_param = "page_size"
    max_page_size = 100