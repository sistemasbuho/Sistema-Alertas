from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.api.formato_mensaje import CrearCamposPlantillaAPIView
from apps.base.models import TemplateConfig
from apps.proyectos.models import Proyecto


class CrearCamposPlantillaAPITests(TestCase):
    """El PUT de campos debe poder eliminar claves de config_campos además
    de crear/actualizar (merge), para que el frontend pueda borrar campos."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.proyecto = Proyecto.objects.create(
            nombre="Proyecto Test",
            codigo_acceso="12345@g.us",
        )
        self.plantilla = TemplateConfig.objects.create(
            nombre="Plantilla Test",
            app_label="base",
            model_name="articulo",
            proyecto=self.proyecto,
            config_campos={
                "titulo": {"orden": 1, "estilo": {"negrita": True}, "label": "Título"},
                "autor": {"orden": 2, "estilo": {}, "label": "Autor"},
            },
        )

    def _put(self, payload):
        request = self.factory.put(
            f"/api/plantillas/{self.plantilla.id}/campos/", payload, format="json"
        )
        force_authenticate(request, user=self.user)
        response = CrearCamposPlantillaAPIView.as_view()(
            request, plantilla_id=self.plantilla.id
        )
        self.plantilla.refresh_from_db()
        return response

    def test_eliminar_borra_campo_de_config(self):
        response = self._put({"campos": [], "eliminar": ["autor"]})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("autor", self.plantilla.config_campos)
        self.assertIn("titulo", self.plantilla.config_campos)

    def test_eliminar_campo_inexistente_no_falla(self):
        response = self._put({"campos": [], "eliminar": ["no_existe"]})
        self.assertEqual(response.status_code, 200)
        self.assertIn("titulo", self.plantilla.config_campos)
        self.assertIn("autor", self.plantilla.config_campos)

    def test_merge_y_eliminacion_en_un_solo_put(self):
        response = self._put(
            {
                "campos": [{"campo": "titulo", "orden": 5}],
                "eliminar": ["autor"],
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("autor", self.plantilla.config_campos)
        self.assertEqual(self.plantilla.config_campos["titulo"]["orden"], 5)
        # El merge conserva las claves no enviadas del campo actualizado
        self.assertEqual(
            self.plantilla.config_campos["titulo"]["estilo"], {"negrita": True}
        )

    def test_put_sin_eliminar_mantiene_comportamiento_actual(self):
        response = self._put({"campos": [{"campo": "reach", "orden": 3}]})
        self.assertEqual(response.status_code, 200)
        self.assertIn("titulo", self.plantilla.config_campos)
        self.assertIn("autor", self.plantilla.config_campos)
        self.assertEqual(self.plantilla.config_campos["reach"]["orden"], 3)
