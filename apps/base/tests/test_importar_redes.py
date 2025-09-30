from django.test import SimpleTestCase

from apps.base.api.importar_redes import ImportarRedesAPIView


class ImportarRedesMapAlertasTests(SimpleTestCase):
    def setUp(self):
        self.view = ImportarRedesAPIView()

    def test_reach_zero_is_preserved(self):
        alerta = {"reach": 0, "alcance": 999}

        resultado = self.view._map_alerta_to_red(alerta)

        self.assertIn("reach", resultado)
        self.assertEqual(resultado["reach"], 0)

    def test_reach_uses_alternative_when_none(self):
        alerta = {"reach": None, "alcance": 0}

        resultado = self.view._map_alerta_to_red(alerta)

        self.assertEqual(resultado["reach"], 0)

    def test_engagement_zero_is_preserved(self):
        alerta = {"engagement": 0, "engammet": 123, "engagement_rate": 456}

        resultado = self.view._map_alerta_to_red(alerta)

        self.assertEqual(resultado["engagement"], 0)

    def test_engagement_falls_back_when_none(self):
        alerta = {"engagement": None, "engammet": None, "engagement_rate": 7}

        resultado = self.view._map_alerta_to_red(alerta)

        self.assertEqual(resultado["engagement"], 7)
