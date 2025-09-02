from django.db import models
from django.conf import settings
from django_currentuser.middleware import get_current_user
import uuid
from simple_history.models import HistoricalRecords



class IdToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

class BaseModel(IdToken):
    created_at = models.DateTimeField('Fecha de creación', auto_now_add=True, editable=False)
    modified_at = models.DateTimeField('Fecha de modificación', auto_now=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Creado por',
        related_name='%(app_label)s_%(class)s_creado_por',
        null=True,
        blank=True,
        default=None,
        on_delete=models.SET_NULL,
        editable=False
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Modificado por',
        related_name='%(app_label)s_%(class)s_modificado_por',
        null=True,
        blank=True,
        default=None,
        on_delete=models.SET_NULL,
        editable=False
    )

    def save(self, *args, **kwargs):
        try:
            user = get_current_user()
        except Exception:
            user = None

        if user and hasattr(user, "id"):
            if self._state.adding:
                self.created_by = user
            self.modified_by = user

        super().save(*args, **kwargs)

    class Meta:
        abstract = True



class Articulo(BaseModel):
    titulo = models.CharField(verbose_name="title", null=True, blank=True)
    contenido = models.TextField(verbose_name="content", null=True, blank=True)
    url = models.URLField(verbose_name="url",max_length=5000, unique=False, blank=True)
    fecha_publicacion = models.DateTimeField(verbose_name="Publicado", null=True, blank=True)
    autor = models.CharField(verbose_name="title", null=True, blank=True)
    reach = models.IntegerField("reach", null=True, blank=True)
    proyecto = models.ForeignKey(
        "proyectos.Proyecto", 
        on_delete=models.CASCADE, 
        related_name="articulos", 
        verbose_name="Proyecto"
    )

class RedesSociales(BaseModel):
    nombre = models.CharField(max_length=100)

class Redes(BaseModel):
    contenido = models.TextField(verbose_name="Contenido",null=True, blank=True)
    fecha = models.DateTimeField(verbose_name="Publicado")
    url = models.URLField(verbose_name="url",max_length=10000, unique=False, blank=True)
    autor =  models.CharField(max_length=100, null=True, blank=True)
    reach = models.IntegerField(null=True, blank=True)
    engagement = models.IntegerField(null=True, blank=True)
    red_social = models.ForeignKey(RedesSociales, models.SET_NULL, null=True, blank=True)
    proyecto = models.ForeignKey(
        "proyectos.Proyecto", 
        on_delete=models.CASCADE, 
        related_name="redes", 
        verbose_name="Proyecto"
    )


class DetalleEnvio(BaseModel):
    inicio_envio = models.DateTimeField()
    fin_envio = models.DateTimeField()
    mensaje = models.TextField(null=True)
    estado_enviado = models.BooleanField(default=False)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,  
        on_delete=models.CASCADE,
        related_name="detalles_envio"
    )

    red_social = models.ForeignKey(
        Redes,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detalles_envio"
    )
    medio = models.ForeignKey(
        Articulo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detalles_envio"
    )

    history = HistoricalRecords(table_name='detalle_envio_history')

    def __str__(self):
        return f"Envio {self.id} - Proyecto: {self.proyecto.nombre}"