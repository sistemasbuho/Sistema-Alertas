from django.db import models
from django.conf import settings
from django_currentuser.middleware import get_current_user
import uuid

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