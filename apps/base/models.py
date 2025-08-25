from django.db import models
from django.conf import settings

import uuid

# Create your models here.
class IdToken(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    class Meta:
        abstract = True

class BaseModel(IdToken):
    created_at = models.DateTimeField('Fecha de creación', auto_now_add=True, editable=False, null=False)
    modified_at = models.DateTimeField('Fecha de modificación', auto_now=True, editable=False, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Creado por', related_name='%(app_label)s_%(class)s_creado_por' ,default=None, blank=True, null=True, on_delete=models.CASCADE,editable = False)
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Modificado por',related_name='%(app_label)s_%(class)s_modificado_por' ,default=None, blank=True, null=True, on_delete=models.CASCADE, editable = False)

    def save(self, *args, **kwargs):
        user = get_current_user()
        if user and user.id:
            if self._state.adding:  # Es una creación
                self.created_by = user
            self.modified_by = user
        super().save(*args, **kwargs)

    class Meta:
        abstract = True

