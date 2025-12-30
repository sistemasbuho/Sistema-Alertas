import django_filters
from django.db.models import Q
from django.utils import timezone
from datetime import datetime
import pytz
from apps.base.models import Redes, Articulo, DetalleEnvio
from rest_framework.pagination import PageNumberPagination


def adjust_datetime_from_utc_to_local(value):
    """
    Ajusta una fecha que viene del frontend con Z (UTC) para interpretarla
    como hora local de Bogotá.

    Ejemplo: Frontend envía 2025-12-26T10:11:00.000Z (queriendo decir 10:11 AM Bogotá)
    pero Django lo interpreta como 10:11 AM UTC = 05:11 AM Bogotá.
    Esta función lo ajusta a 10:11 AM Bogotá.
    """
    if value is None:
        return None

    # Obtener la zona horaria configurada en Django
    local_tz = timezone.get_current_timezone()

    # Si viene como aware (con timezone), obtener la hora naive
    if timezone.is_aware(value):
        # La fecha viene como UTC, extraer solo los valores de fecha/hora
        naive_dt = datetime(
            value.year, value.month, value.day,
            value.hour, value.minute, value.second,
            value.microsecond
        )
    else:
        naive_dt = value

    # Convertir la fecha naive a timezone-aware en la zona horaria local
    # Compatible con ZoneInfo (Python 3.9+) y pytz
    local_dt = naive_dt.replace(tzinfo=local_tz)

    return local_dt



class RedesFilter(django_filters.FilterSet):
    fecha_inicio = django_filters.DateFilter(field_name="created_at", lookup_expr="gte")
    fecha_fin = django_filters.DateFilter(field_name="created_at", lookup_expr="lte")
    created_at_desde = django_filters.DateTimeFilter(method="filter_created_at_desde")
    created_at_hasta = django_filters.DateTimeFilter(method="filter_created_at_hasta")
    autor = django_filters.CharFilter(field_name="autor", lookup_expr="icontains")
    url = django_filters.CharFilter(field_name="url", lookup_expr="exact")
    url_coincide = django_filters.CharFilter(field_name="url", lookup_expr="icontains")
    proyecto = django_filters.CharFilter(method="filter_proyecto")
    red_social_nombre = django_filters.CharFilter(field_name="red_social__nombre", lookup_expr="icontains")
    created_by = django_filters.NumberFilter(field_name="created_by__id")
    created_by_username = django_filters.CharFilter(field_name="created_by__username", lookup_expr="icontains")
    usuario_nombre = django_filters.CharFilter(field_name="created_by__username", lookup_expr="icontains")
    estado_enviado = django_filters.BooleanFilter(method="filter_estado_enviado")
    estado_revisado = django_filters.BooleanFilter(method="filter_estado_revisado")

    class Meta:
        model = Redes
        fields = [
            "autor",
            "url",
            "url_coincide",
            "proyecto",
            "red_social_nombre",
            "fecha_inicio",
            "fecha_fin",
            "created_at_desde",
            "created_at_hasta",
            "created_by",
            "created_by_username",
            "usuario_nombre",
            "estado_enviado",
            "estado_revisado",
        ]

    def filter_created_at_desde(self, queryset, name, value):
        if value is None:
            return queryset
        adjusted_value = adjust_datetime_from_utc_to_local(value)
        return queryset.filter(created_at__gte=adjusted_value)

    def filter_created_at_hasta(self, queryset, name, value):
        if value is None:
            return queryset
        adjusted_value = adjust_datetime_from_utc_to_local(value)
        return queryset.filter(created_at__lte=adjusted_value)

    def filter_estado_enviado(self, queryset, name, value):
        if value is None:
            return queryset
        if value:
            # Todos los detalles enviados y ninguno pendiente
            return queryset.filter(detalles_envio__estado_enviado=True).exclude(detalles_envio__estado_enviado=False).distinct()
        return queryset.filter(detalles_envio__estado_enviado=False).distinct()

    def filter_estado_revisado(self, queryset, name, value):
        if value is None:
            return queryset
        if value:
            return queryset.filter(detalles_envio__estado_revisado=True).exclude(detalles_envio__estado_revisado=False).distinct()
        return queryset.filter(detalles_envio__estado_revisado=False).distinct()

    def filter_proyecto(self, queryset, name, value):
        if not value:
            return queryset
        import uuid
        try:
            uuid.UUID(value)
            return queryset.filter(Q(proyecto_id=value) | Q(proyecto__nombre__icontains=value))
        except (ValueError, AttributeError):
            return queryset.filter(proyecto__nombre__icontains=value)

class MediosFilter(django_filters.FilterSet):
    fecha_inicio = django_filters.DateFilter(field_name="created_at", lookup_expr="gte")
    fecha_fin = django_filters.DateFilter(field_name="created_at", lookup_expr="lte")
    created_at_desde = django_filters.DateTimeFilter(method="filter_created_at_desde")
    created_at_hasta = django_filters.DateTimeFilter(method="filter_created_at_hasta")
    fuente = django_filters.CharFilter(field_name="fuente", lookup_expr="icontains")
    tipo_medio = django_filters.CharFilter(field_name="tipo_medio", lookup_expr="icontains")
    url = django_filters.CharFilter(field_name="url", lookup_expr="exact")
    url_coincide = django_filters.CharFilter(field_name="url", lookup_expr="icontains")
    autor = django_filters.CharFilter(field_name="autor", lookup_expr="icontains")

    ciudad = django_filters.CharFilter(field_name="ciudad", lookup_expr="icontains")
    proyecto = django_filters.CharFilter(method="filter_proyecto")
    created_by = django_filters.NumberFilter(field_name="created_by__id")
    created_by_username = django_filters.CharFilter(field_name="created_by__username", lookup_expr="icontains")
    usuario_nombre = django_filters.CharFilter(field_name="created_by__username", lookup_expr="icontains")
    estado_enviado = django_filters.BooleanFilter(method="filter_estado_enviado")
    estado_revisado = django_filters.BooleanFilter(method="filter_estado_revisado")


    class Meta:
        model = Articulo
        fields = [
            "fuente",
            "tipo_medio",
            "url",
            "url_coincide",
            "ciudad",
            "proyecto",
            "fecha_inicio",
            "fecha_fin",
            "created_at_desde",
            "created_at_hasta",
            "created_by",
            "created_by_username",
            "usuario_nombre",
            "estado_enviado",
            "estado_revisado",
            "autor",
        ]

    def filter_created_at_desde(self, queryset, name, value):
        if value is None:
            return queryset
        adjusted_value = adjust_datetime_from_utc_to_local(value)
        return queryset.filter(created_at__gte=adjusted_value)

    def filter_created_at_hasta(self, queryset, name, value):
        if value is None:
            return queryset
        adjusted_value = adjust_datetime_from_utc_to_local(value)
        return queryset.filter(created_at__lte=adjusted_value)

    def filter_estado_enviado(self, queryset, name, value):
        if value is None:
            return queryset
        if value:
            return queryset.filter(detalles_envio__estado_enviado=True).exclude(detalles_envio__estado_enviado=False).distinct()
        return queryset.filter(detalles_envio__estado_enviado=False).distinct()

    def filter_estado_revisado(self, queryset, name, value):
        if value is None:
            return queryset
        if value:
            return queryset.filter(detalles_envio__estado_revisado=True).exclude(detalles_envio__estado_revisado=False).distinct()
        return queryset.filter(detalles_envio__estado_revisado=False).distinct()

    def filter_proyecto(self, queryset, name, value):
        if not value:
            return queryset
        import uuid
        try:
            uuid.UUID(value)
            return queryset.filter(Q(proyecto_id=value) | Q(proyecto__nombre__icontains=value))
        except (ValueError, AttributeError):
            return queryset.filter(proyecto__nombre__icontains=value)


class DetalleEnvioFilter(django_filters.FilterSet):
    usuario_nombre = django_filters.CharFilter(method="filter_usuario_creador")
    proyecto_nombre = django_filters.CharFilter(field_name="proyecto__nombre", lookup_expr="icontains")
    proyecto = django_filters.CharFilter(method="filter_proyecto")
    estado_enviado = django_filters.BooleanFilter(field_name="estado_enviado")
    estado_revisado = django_filters.BooleanFilter(field_name="estado_revisado")
    autor = django_filters.CharFilter(method="filter_autor")
    url = django_filters.CharFilter(method="filter_url_exacta")
    url_coincide = django_filters.CharFilter(method="filter_url_coincide")
    created_at_desde = django_filters.DateTimeFilter(method="filter_created_at_desde")
    created_at_hasta = django_filters.DateTimeFilter(method="filter_created_at_hasta")
    inicio_envio_desde = django_filters.DateTimeFilter(method="filter_inicio_envio_desde")
    fin_envio_hasta = django_filters.DateTimeFilter(method="filter_fin_envio_hasta")
    medio_url = django_filters.CharFilter(field_name="medio__url", lookup_expr="exact")
    medio_url_coincide = django_filters.CharFilter(field_name="medio__url", lookup_expr="icontains")
    red_social_nombre = django_filters.CharFilter(field_name="red_social__red_social__nombre", lookup_expr="icontains")

    class Meta:
        model = DetalleEnvio
        fields = [
            "usuario_nombre",
            "proyecto_nombre",
            "proyecto",
            "autor",
            "estado_enviado",
            "estado_revisado",
            "url",
            "url_coincide",
            "created_at_desde",
            "created_at_hasta",
            "inicio_envio_desde",
            "fin_envio_hasta",
            "medio_url",
            "medio_url_coincide",
            "red_social_nombre",
        ]

    def filter_created_at_desde(self, queryset, name, value):
        if value is None:
            return queryset
        adjusted_value = adjust_datetime_from_utc_to_local(value)
        return queryset.filter(created_at__gte=adjusted_value)

    def filter_created_at_hasta(self, queryset, name, value):
        if value is None:
            return queryset
        adjusted_value = adjust_datetime_from_utc_to_local(value)
        return queryset.filter(created_at__lte=adjusted_value)

    def filter_inicio_envio_desde(self, queryset, name, value):
        if value is None:
            return queryset
        adjusted_value = adjust_datetime_from_utc_to_local(value)
        return queryset.filter(inicio_envio__gte=adjusted_value)

    def filter_fin_envio_hasta(self, queryset, name, value):
        if value is None:
            return queryset
        adjusted_value = adjust_datetime_from_utc_to_local(value)
        return queryset.filter(fin_envio__lte=adjusted_value)

    def filter_proyecto(self, queryset, name, value):
        if not value:
            return queryset
        import uuid
        try:
            uuid.UUID(value)
            # Es UUID válido, buscar por ID o nombre
            return queryset.filter(
                Q(proyecto_id=value)
                | Q(proyecto__nombre__icontains=value)
                | Q(medio__proyecto_id=value)
                | Q(medio__proyecto__nombre__icontains=value)
                | Q(red_social__proyecto_id=value)
                | Q(red_social__proyecto__nombre__icontains=value)
            ).distinct()
        except (ValueError, AttributeError):
            # No es UUID, solo buscar por nombre
            return queryset.filter(
                Q(proyecto__nombre__icontains=value)
                | Q(medio__proyecto__nombre__icontains=value)
                | Q(red_social__proyecto__nombre__icontains=value)
            ).distinct()

    def filter_autor(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(medio__autor__icontains=value) | Q(red_social__autor__icontains=value)
        )

    def filter_url_exacta(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(Q(medio__url=value) | Q(red_social__url=value))

    def filter_url_coincide(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(medio__url__icontains=value) | Q(red_social__url__icontains=value)
        )

    def filter_usuario_creador(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(medio__created_by__username__icontains=value)
            | Q(red_social__created_by__username__icontains=value)
        )


class PaginacionEstandar(PageNumberPagination):
    page_size = 50  
    page_size_query_param = "page_size"
    max_page_size = 100
