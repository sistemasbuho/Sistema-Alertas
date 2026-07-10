from django.db import models
from django.conf import settings
from django.utils import timezone
from django_currentuser.middleware import get_current_user
import uuid
from simple_history.models import HistoricalRecords
from apps.proyectos.models import Proyecto



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
        on_delete=models.SET_NULL,
        editable=False
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Modificado por',
        related_name='%(app_label)s_%(class)s_modificado_por',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        editable=False
    )

    def save(self, *args, **kwargs):
        try:
            user = get_current_user()
        except Exception:
            user = None

        if user and getattr(user, "is_authenticated", False):
            if self._state.adding and not self.created_by:
                self.created_by = user
            self.modified_by = user

        super().save(*args, **kwargs)

    class Meta:
        abstract = True  # ← Esto es lo que falta




class Articulo(BaseModel):
    titulo = models.CharField(verbose_name="title", max_length=500, null=True, blank=True)
    contenido = models.TextField(verbose_name="content", null=True, blank=True)
    url = models.URLField(verbose_name="url",max_length=5000, unique=False, blank=True)
    fecha_publicacion = models.DateTimeField(verbose_name="Publicado", null=True, blank=True)
    autor = models.CharField(verbose_name="title", max_length=600, null=True, blank=True)
    fuente = models.CharField(verbose_name="Fuente/Medio", max_length=600, null=True, blank=True)
    tipo_medio = models.CharField(verbose_name="Tipo de Medio", max_length=200, null=True, blank=True)
    reach = models.IntegerField("reach", null=True, blank=True)
    engagement = models.IntegerField(null=True, blank=True)
    ubicacion = models.CharField(verbose_name="Ubicación", max_length=200, null=True, blank=True)
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
    fecha_publicacion = models.DateTimeField(verbose_name="Publicado")
    url = models.URLField(verbose_name="url",max_length=10000, unique=False, blank=True)
    autor =  models.CharField(max_length=600, null=True, blank=True)
    reach = models.IntegerField(null=True, blank=True)
    engagement = models.IntegerField(null=True, blank=True)
    ubicacion = models.CharField(verbose_name="Ubicación", max_length=200, null=True, blank=True)
    red_social = models.ForeignKey(RedesSociales, models.SET_NULL, null=True, blank=True)
    proyecto = models.ForeignKey(
        "proyectos.Proyecto",
        on_delete=models.CASCADE,
        related_name="redes",
        verbose_name="Proyecto"
    )


class DetalleEnvio(BaseModel):
    # Estados del pipeline IA. "manual" = flujo legacy sin IA (default para
    # proyectos sin matriz activa y filas anteriores al sprint).
    PIPELINE_MANUAL = "manual"
    PIPELINE_PENDIENTE_IA = "pendiente_ia"
    PIPELINE_CLASIFICANDO = "clasificando"
    PIPELINE_ENRIQUECIENDO = "enriqueciendo"
    PIPELINE_AUTO_APROBADA = "auto_aprobada"
    PIPELINE_COLA_EXCEPCIONES = "cola_excepciones"
    PIPELINE_APROBADA_HUMANA = "aprobada_humana"
    PIPELINE_DESCARTADA_IA = "descartada_ia"
    PIPELINE_DESCARTADA_HUMANA = "descartada_humana"
    PIPELINE_ENVIADA = "enviada"
    PIPELINE_ERROR_ENVIO = "error_envio"

    ESTADO_PIPELINE_CHOICES = [
        (PIPELINE_MANUAL, "Manual / legacy"),
        (PIPELINE_PENDIENTE_IA, "Pendiente IA"),
        (PIPELINE_CLASIFICANDO, "Clasificando"),
        (PIPELINE_ENRIQUECIENDO, "Enriqueciendo"),
        (PIPELINE_AUTO_APROBADA, "Auto-aprobada"),
        (PIPELINE_COLA_EXCEPCIONES, "Cola de excepciones"),
        (PIPELINE_APROBADA_HUMANA, "Aprobada por humano"),
        (PIPELINE_DESCARTADA_IA, "Descartada por IA"),
        (PIPELINE_DESCARTADA_HUMANA, "Descartada por humano"),
        (PIPELINE_ENVIADA, "Enviada"),
        (PIPELINE_ERROR_ENVIO, "Error de envío"),
    ]

    inicio_envio = models.DateTimeField(null=True)
    fin_envio = models.DateTimeField(null=True)
    mensaje = models.TextField(null=True)
    estado_enviado = models.BooleanField(default=False)
    estado_revisado = models.BooleanField(default=False)
    estado_pipeline = models.CharField(
        max_length=20,
        choices=ESTADO_PIPELINE_CHOICES,
        default=PIPELINE_MANUAL,
        db_index=True,
    )
    proveedor_envio = models.CharField(max_length=20, null=True, blank=True)
    intentos_ia = models.PositiveSmallIntegerField(default=0)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,  
        on_delete=models.CASCADE,
        related_name="detalles_envio",
        null=True,
        blank=True
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

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="detalles_envio",
        null=True,
        blank=True
    )

    history = HistoricalRecords(table_name='detalle_envio_history')

    def aplicar_estado_pipeline(self, estado, guardar=True):
        """Transiciona el estado del pipeline manteniendo sincronizados los
        booleanos legacy que consume el frontend actual."""
        self.estado_pipeline = estado

        if estado == self.PIPELINE_ENVIADA:
            self.estado_enviado = True
            if not self.fin_envio:
                self.fin_envio = timezone.now()
        elif estado == self.PIPELINE_ERROR_ENVIO:
            self.estado_enviado = False
        elif estado == self.PIPELINE_COLA_EXCEPCIONES:
            self.estado_revisado = False
        elif estado in (
            self.PIPELINE_APROBADA_HUMANA,
            self.PIPELINE_DESCARTADA_HUMANA,
            self.PIPELINE_DESCARTADA_IA,
        ):
            self.estado_revisado = True

        if guardar:
            self.save()

    def __str__(self):
        proyecto_nombre = None
        if self.medio and self.medio.proyecto:
            proyecto_nombre = self.medio.proyecto.nombre
        elif self.red_social and self.red_social.proyecto:
            proyecto_nombre = self.red_social.proyecto.nombre

        return f"Envio {self.id} - Proyecto: {proyecto_nombre}"



class TemplateConfig(BaseModel):
    nombre = models.CharField(max_length=150)
    app_label = models.CharField(max_length=100) 
    model_name = models.CharField(max_length=100)  
    config_campos = models.JSONField(default=dict, blank=True)
    proyecto = models.ForeignKey(
        "proyectos.Proyecto", 
        on_delete=models.CASCADE, 
        related_name="plantillas"
    )

    def get_model_fields(self):
        from django.apps import apps
        Model = apps.get_model(self.app_label, self.model_name)
        return [f.name for f in Model._meta.get_fields() if f.concrete]

class TemplateCampoConfig(BaseModel):
    plantilla = models.ForeignKey(
        TemplateConfig,
        on_delete=models.CASCADE,
        related_name="campos"
    )
    campo = models.CharField(max_length=100)
    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    estilo = models.JSONField(default=dict, blank=True)