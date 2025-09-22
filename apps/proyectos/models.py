from django.db import models
from django.conf import settings
import uuid


# Create your models here.
class Proyecto(models.Model):
    """
    Modelo para gestionar proyectos del sistema
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Opciones para campos de selección
    ESTADO_CHOICES = [
        ('activo', 'Activo'),
        ('inactivo', 'Inactivo'),
        ('pendiente', 'Pendiente'),
        ('completado', 'Completado'),
    ]
    
    TIPO_ENVIO_CHOICES = [
        ('automatico', 'Automatico'),
        ('programado', 'Programado'),
        ('manual', 'Manual'),
    ]
    
    TIPO_ALERTA_CHOICES = [
        ('redes', 'Redes'),
        ('medios', 'Medios'),
    ]

    FORMATO_MENSAJE_CHOICES = [
        ('uno a uno', 'Uno a uno'),
        ('muchos en uno', 'Muchos en uno'),
    ]
    
        
    nombre = models.CharField(
        'Nombre del proyecto', 
        max_length=500, 
        help_text="Nombre descriptivo del proyecto"
    )


    proveedor = models.CharField(
        'Nombre del proveedor', 
        max_length=500, 
        unique=False,
        help_text="Nombre descriptivo del proveedor"
    )
    
    codigo_acceso = models.CharField(
        'Código de acceso', 
        max_length=100, 
        unique=False,
        help_text="Código único para acceder al proyecto"
    )
    
    nombre_grupo = models.CharField(
        'Nombre del nombre_grupo', 
        max_length=500, 
        help_text="Nombre del grupo",
        blank=True, 
        null=True,
    )

    estado = models.CharField(
        'Estado', 
        max_length=20, 
        choices=ESTADO_CHOICES, 
        default='activo',
        help_text="Estado actual del proyecto"
    )
    
    tipo_envio = models.CharField(
        'Tipo de envío', 
        max_length=20, 
        choices=TIPO_ENVIO_CHOICES, 
        default='manual',
        help_text="Modalidad de envío de mensajes"
    )
    
    tipo_alerta = models.CharField(
        'Tipo de alerta', 
        max_length=20, 
        choices=TIPO_ALERTA_CHOICES, 
        default='medios',
        help_text="Tipo de notificación a enviar"
    )
    

    formato_mensaje = models.CharField(
        'Formato mensaje', 
        max_length=20, 
        choices=FORMATO_MENSAJE_CHOICES, 
        default='uno a uno',
        help_text="Formato mensaje a enviar"
    )
    
    keywords = models.TextField(
        'Palabras clave', 
        blank=True, 
        null=True,
        help_text="Palabras clave separadas por comas para filtrar mensajes"
    )

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

    

    class Meta:
        verbose_name = 'Proyecto'
        verbose_name_plural = 'Proyectos'

        indexes = [
            models.Index(fields=['nombre']),
            models.Index(fields=['codigo_acceso']),
            models.Index(fields=['estado']),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.codigo_acceso})"
    
    def get_keywords_list(self):
        """
        Devuelve las palabras clave como lista
        """
        if self.keywords:
            return [keyword.strip() for keyword in self.keywords.split(',')]
        return []
    
    def set_keywords(self, keywords_list):
        """
        Establece las palabras clave desde una lista
        """
        self.keywords = ', '.join([str(keyword).strip() for keyword in keywords_list])



