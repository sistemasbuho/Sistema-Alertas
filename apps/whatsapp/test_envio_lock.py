"""Regresión: el envío del pipeline IA hacía `select_for_update()` junto a
`select_related()` sobre FKs nullable (`red_social`, `medio`), lo que en
PostgreSQL revienta con:

    NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an
    outer join

El fix bloquea solo la fila de DetalleEnvio con `select_for_update(of=("self",))`.
El mismo patrón vive en apps/ia/api/resolver_excepcion.py (aprobación humana).

Solo tiene sentido en PostgreSQL: en SQLite `select_for_update` es un no-op y el
test pasaría incluso con el bug (falso verde), por eso se salta fuera de Postgres.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.base.models import Articulo, DetalleEnvio
from apps.proyectos.models import Proyecto


class EnviarDetalleForUpdateJoinNullableTests(TestCase):
    def setUp(self):
        self.proyecto = Proyecto.objects.create(
            nombre="Prueba lock",
            codigo_acceso="120363000000000000@g.us",
            tipo_alerta="medios",
        )
        # medio seteado y red_social NULL: el escenario que produce el LEFT JOIN
        self.articulo = Articulo.objects.create(
            proyecto=self.proyecto,
            titulo="Titulo",
            contenido="Contenido de prueba",
            url="https://example.com/nota",
            autor="Autor",
            fecha_publicacion=timezone.now(),
        )
        self.detalle = DetalleEnvio.objects.create(
            proyecto=self.proyecto,
            medio=self.articulo,
            estado_pipeline=DetalleEnvio.PIPELINE_AUTO_APROBADA,
            estado_enviado=False,
        )

    def test_auto_aprobada_se_envia_sin_notsupported(self):
        """`enviar_detalle` no debe romper por FOR UPDATE sobre el join nullable
        y debe entregar la alerta (envío WHAPI mockeado)."""
        if connection.vendor != "postgresql":
            self.skipTest("El bug FOR UPDATE/outer-join solo aplica en PostgreSQL")

        from apps.whatsapp.services.envio import enviar_detalle

        exito = SimpleNamespace(exito=True, proveedor="TEST-MOCK", detalle="")
        with patch(
            "apps.whatsapp.services.envio.enviar_texto", return_value=exito
        ) as mock_enviar, patch(
            "apps.whatsapp.api.enviar_mensaje.enviar_alertas_a_monitoreo",
            return_value=None,
        ):
            resultado = enviar_detalle(str(self.detalle.id))

        self.assertEqual(resultado, "enviada")
        mock_enviar.assert_called_once()
        self.detalle.refresh_from_db()
        self.assertTrue(self.detalle.estado_enviado)
        self.assertEqual(self.detalle.estado_pipeline, DetalleEnvio.PIPELINE_ENVIADA)
