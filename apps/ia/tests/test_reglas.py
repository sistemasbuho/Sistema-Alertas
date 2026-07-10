from django.test import SimpleTestCase

from apps.ia.services import reglas

CONFIG_SEMAFORO_LOREAL = {
    "tipo": "riesgo_engagement_reach",
    "engagement_alto": {
        "twitter": 100,
        "facebook": 150,
        "instagram": 500,
        "tiktok": 500,
        "default": 500,
    },
    "reach_niveles": {"bajo": [500, 1000], "medio": [1000, 8000], "alto": 8000},
    "emojis": {"bajo": "🟢", "medio": "🟡", "alto": "🔴"},
}


class SemaforoRiesgoTests(SimpleTestCase):
    """Tabla de decisión del semáforo L'Oréal: bajo=ninguna variable alta,
    medio=una alta, alto=ambas altas."""

    def _riesgo(self, red, engagement, reach):
        return reglas.calcular_semaforo(
            CONFIG_SEMAFORO_LOREAL, red_social=red, engagement=engagement, reach=reach
        )

    def test_ninguna_alta_es_bajo(self):
        resultado = self._riesgo("twitter", 50, 600)
        self.assertEqual(resultado["riesgo"], "bajo")
        self.assertEqual(resultado["emoji"], "🟢")

    def test_solo_engagement_alto_es_medio(self):
        # X: engagement alto es > 100
        self.assertEqual(self._riesgo("twitter", 101, 600)["riesgo"], "medio")
        self.assertEqual(self._riesgo("twitter", 100, 600)["riesgo"], "bajo")

    def test_solo_reach_alto_es_medio(self):
        # reach alto es > 8000
        resultado = self._riesgo("facebook", 10, 8001)
        self.assertEqual(resultado["riesgo"], "medio")
        self.assertEqual(resultado["emoji"], "🟡")

    def test_ambas_altas_es_alto(self):
        resultado = self._riesgo("instagram", 501, 9000)
        self.assertEqual(resultado["riesgo"], "alto")
        self.assertEqual(resultado["emoji"], "🔴")

    def test_umbral_por_red(self):
        # FB: >150, IG/TikTok: >500
        self.assertEqual(self._riesgo("facebook", 151, 100)["riesgo"], "medio")
        self.assertEqual(self._riesgo("facebook", 150, 100)["riesgo"], "bajo")
        self.assertEqual(self._riesgo("tiktok", 500, 100)["riesgo"], "bajo")
        self.assertEqual(self._riesgo("tiktok", 501, 100)["riesgo"], "medio")

    def test_red_desconocida_usa_default(self):
        self.assertEqual(self._riesgo("linkedin", 501, 100)["riesgo"], "medio")

    def test_valores_nulos_no_rompen(self):
        resultado = self._riesgo("twitter", None, None)
        self.assertEqual(resultado["riesgo"], "bajo")

    def test_semaforo_por_tonalidad(self):
        config = {"tipo": "tonalidad", "emojis": {"positivo": "🟢", "neutral": "🟡", "negativo": "🔴"}}
        resultado = reglas.calcular_semaforo(config, tonalidad="negativo")
        self.assertEqual(resultado["emoji"], "🔴")

    def test_config_vacia_devuelve_none(self):
        self.assertIsNone(reglas.calcular_semaforo({}, red_social="x"))


class BanderaTests(SimpleTestCase):
    def test_bandera_peru(self):
        self.assertEqual(reglas.bandera("PE"), "🇵🇪")

    def test_bandera_colombia_minuscula(self):
        self.assertEqual(reglas.bandera("co"), "🇨🇴")

    def test_bandera_invalida(self):
        self.assertIsNone(reglas.bandera(None))
        self.assertIsNone(reglas.bandera("XXX"))
        self.assertIsNone(reglas.bandera("1A"))


class ReglasPreviasTests(SimpleTestCase):
    REGLAS = [
        {"tipo": "min_seguidores", "valor": 500, "ejecutor": "codigo"},
        {"tipo": "pais_fuera_lista", "ejecutor": "codigo"},
        {"tipo": "semantica", "clave": "precio_negativo", "ejecutor": "llm"},
    ]

    def test_min_seguidores_descarta(self):
        alerta = {"reach": 300, "ubicacion": None}
        aplicadas = reglas.evaluar_reglas_previas(self.REGLAS, alerta, paises=["PE"])
        self.assertTrue(any(r["regla"] == "min_seguidores" for r in aplicadas))

    def test_min_seguidores_pasa(self):
        alerta = {"reach": 900, "ubicacion": None}
        aplicadas = reglas.evaluar_reglas_previas(self.REGLAS, alerta, paises=["PE"])
        self.assertFalse(any(r["regla"] == "min_seguidores" for r in aplicadas))

    def test_reach_desconocido_no_descarta(self):
        # Sin dato no se puede aplicar la regla: se deja pasar (la IA/humano decide)
        alerta = {"reach": None, "ubicacion": None}
        aplicadas = reglas.evaluar_reglas_previas(self.REGLAS, alerta, paises=["PE"])
        self.assertEqual(aplicadas, [])

    def test_pais_fuera_de_lista_descarta(self):
        alerta = {"reach": 900, "ubicacion": "España"}
        aplicadas = reglas.evaluar_reglas_previas(self.REGLAS, alerta, paises=["PE", "CO"])
        self.assertTrue(any(r["regla"] == "pais_fuera_lista" for r in aplicadas))

    def test_pais_en_lista_pasa(self):
        alerta = {"reach": 900, "ubicacion": "Perú"}
        aplicadas = reglas.evaluar_reglas_previas(self.REGLAS, alerta, paises=["PE", "CO"])
        self.assertEqual(aplicadas, [])

    def test_reglas_llm_no_se_evaluan_en_codigo(self):
        alerta = {"reach": 100}
        aplicadas = reglas.evaluar_reglas_previas(
            [{"tipo": "semantica", "clave": "x", "ejecutor": "llm"}], alerta, paises=[]
        )
        self.assertEqual(aplicadas, [])


class ConfianzaTests(SimpleTestCase):
    def test_confianza_es_minimo_de_scores(self):
        salida = {"relevancia_score": 0.9, "tonalidad_score": 0.7, "pais_score": 0.95}
        self.assertEqual(reglas.calcular_confianza(salida, requiere_pais=True), 0.7)

    def test_sin_bandera_ignora_pais(self):
        salida = {"relevancia_score": 0.9, "tonalidad_score": 0.85, "pais_score": 0.2}
        self.assertEqual(reglas.calcular_confianza(salida, requiere_pais=False), 0.85)

    def test_scores_faltantes_son_cero(self):
        self.assertEqual(reglas.calcular_confianza({}, requiere_pais=False), 0.0)
