import django_filters
from .models import Redes, Medios

class RedesFilter(django_filters.FilterSet):
    fecha_inicio = django_filters.DateFilter(field_name="fecha", lookup_expr="gte")
    fecha_fin = django_filters.DateFilter(field_name="fecha", lookup_expr="lte")
    autor = django_filters.CharFilter(field_name="autor", lookup_expr="icontains")
    url = django_filters.CharFilter(field_name="url", lookup_expr="icontains")
    proyecto = django_filters.CharFilter(field_name="proyecto__nombre", lookup_expr="icontains")

    class Meta:
        model = Redes
        fields = ["autor", "url", "proyecto", "fecha_inicio", "fecha_fin"]

class MediosFilter(django_filters.FilterSet):
    fecha_inicio = django_filters.DateFilter(field_name="fecha", lookup_expr="gte")
    fecha_fin = django_filters.DateFilter(field_name="fecha", lookup_expr="lte")
    medio = django_filters.CharFilter(field_name="medio", lookup_expr="icontains")
    ciudad = django_filters.CharFilter(field_name="ciudad", lookup_expr="icontains")
    proyecto = django_filters.CharFilter(field_name="proyecto__nombre", lookup_expr="icontains")

    class Meta:
        model = Medios
        fields = ["medio", "ciudad", "proyecto", "fecha_inicio", "fecha_fin"]
