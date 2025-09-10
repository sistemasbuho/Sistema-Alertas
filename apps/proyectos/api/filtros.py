import django_filters
from apps.proyectos.models import Proyecto

class ProyectoFilter(django_filters.FilterSet):
    nombre = django_filters.CharFilter(field_name="nombre", lookup_expr="icontains")

    class Meta:
        model = Proyecto
        fields = ["nombre"]