from django.core.management import call_command
from django.test import TestCase

from apps.ia.models import MatrizCliente
from apps.proyectos.models import Proyecto


class MatrizClienteTests(TestCase):
    def setUp(self):
        self.proyecto = Proyecto.objects.create(
            nombre="LOREAL",
            codigo_acceso="loreal@g.us",
            tipo_alerta="redes",
        )

    def test_seed_loreal_crea_matriz(self):
        call_command("cargar_matriz_loreal", str(self.proyecto.id))
        matriz = MatrizCliente.objects.get(proyecto=self.proyecto)

        self.assertFalse(matriz.activo)
        self.assertEqual(matriz.modo, "sombra")
        self.assertIn("Lancôme", matriz.marcas)
        self.assertIn("Garnier", matriz.marcas)
        self.assertEqual(len(matriz.paises), 15)
        self.assertIn("PE", matriz.paises)
        self.assertTrue(matriz.incluir_bandera)
        self.assertTrue(matriz.incluir_semaforo)

        # Semáforo de riesgo determinístico (números de la matriz del cliente)
        semaforo = matriz.config_semaforo
        self.assertEqual(semaforo["tipo"], "riesgo_engagement_reach")
        self.assertEqual(semaforo["engagement_alto"]["twitter"], 100)
        self.assertEqual(semaforo["engagement_alto"]["facebook"], 150)
        self.assertEqual(semaforo["engagement_alto"]["instagram"], 500)
        self.assertEqual(semaforo["reach_niveles"]["alto"], 8000)

        # Umbrales por tipo
        self.assertIn("redes", matriz.umbral_confianza)
        self.assertIn("auto_envio", matriz.umbral_confianza["redes"])

        # Para L'Oréal lo negativo ES el producto: sin reglas nunca-autoenviar
        self.assertEqual(matriz.reglas_nunca_autoenviar, [])

        # Reglas no-alertar divididas por ejecutor
        ejecutores = {r["ejecutor"] for r in matriz.reglas_no_alertar}
        self.assertEqual(ejecutores, {"codigo", "llm"})

    def test_seed_es_idempotente(self):
        call_command("cargar_matriz_loreal", str(self.proyecto.id))
        call_command("cargar_matriz_loreal", str(self.proyecto.id))
        self.assertEqual(
            MatrizCliente.objects.filter(proyecto=self.proyecto).count(), 1
        )

    def test_seed_con_activar(self):
        call_command("cargar_matriz_loreal", str(self.proyecto.id), "--activar")
        matriz = MatrizCliente.objects.get(proyecto=self.proyecto)
        self.assertTrue(matriz.activo)
        self.assertEqual(matriz.modo, "sombra")
