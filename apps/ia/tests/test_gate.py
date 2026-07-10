from django.test import TestCase
from django.utils import timezone

from apps.base.models import DetalleEnvio, Redes, RedesSociales
from apps.ia.models import EvaluacionIA, MatrizCliente
from apps.ia.services.gate import decidir
from apps.proyectos.models import Proyecto


def _salida(relevante=True, rel=0.95, ton="negativo", ton_s=0.9, pais="PE", pais_s=0.95):
    return {
        "relevante": relevante,
        "relevancia_score": rel,
        "tonalidad": ton,
        "tonalidad_score": ton_s,
        "pais": pais,
        "pais_score": pais_s,
        "categoria_sector": "belleza",
        "regla_no_alertar": None,
        "marca_detectada": "Garnier",
        "razones": ["mención negativa de Garnier"],
    }


class GateTests(TestCase):
    def setUp(self):
        self.proyecto = Proyecto.objects.create(
            nombre="LOREAL", codigo_acceso="g@g.us", tipo_alerta="redes"
        )
        self.matriz = MatrizCliente.objects.create(
            proyecto=self.proyecto,
            activo=True,
            modo=MatrizCliente.MODO_ACTIVO,
            paises=["PE", "CO", "MX"],
            umbral_confianza={"redes": {"auto_envio": 0.85, "descarte": 0.90}},
            reglas_nunca_autoenviar=[],
            incluir_bandera=True,
            incluir_semaforo=True,
            config_semaforo={
                "tipo": "riesgo_engagement_reach",
                "engagement_alto": {"twitter": 100, "default": 500},
                "reach_niveles": {"bajo": [500, 1000], "medio": [1000, 8000], "alto": 8000},
                "emojis": {"bajo": "🟢", "medio": "🟡", "alto": "🔴"},
            },
            campos_requeridos_envio={"redes": ["reach", "engagement"]},
        )
        red_social = RedesSociales.objects.create(nombre="Twitter")
        self.red = Redes.objects.create(
            contenido="Garnier me quemó el cuero cabelludo",
            fecha_publicacion=timezone.now(),
            url="https://twitter.com/u/status/1",
            autor="@usuario",
            reach=2000,
            engagement=50,
            red_social=red_social,
            proyecto=self.proyecto,
        )
        self.detalle = DetalleEnvio.objects.create(
            proyecto=self.proyecto,
            red_social=self.red,
            estado_pipeline=DetalleEnvio.PIPELINE_CLASIFICANDO,
        )

    def _decidir(self, salida, matriz=None):
        return decidir(
            matriz=matriz or self.matriz,
            detalle=self.detalle,
            salida=salida,
            tipo_alerta="redes",
            alerta={
                "reach": self.red.reach,
                "engagement": self.red.engagement,
                "red_social": "twitter",
            },
        )

    def test_alta_confianza_auto_envia(self):
        decision = self._decidir(_salida())
        self.assertEqual(decision["decision"], EvaluacionIA.DECISION_AUTO_ENVIAR)
        self.assertEqual(decision["estado_pipeline"], DetalleEnvio.PIPELINE_AUTO_APROBADA)
        # reach 2000 no supera "alto" (>8000) y engagement 50 < 100: ninguna variable alta
        self.assertEqual(decision["riesgo"], "bajo")

    def test_confianza_baja_va_a_cola(self):
        decision = self._decidir(_salida(ton_s=0.5))
        self.assertEqual(decision["decision"], EvaluacionIA.DECISION_COLA)
        self.assertEqual(decision["estado_pipeline"], DetalleEnvio.PIPELINE_COLA_EXCEPCIONES)

    def test_irrelevante_con_certeza_descarta(self):
        decision = self._decidir(_salida(relevante=False, rel=0.95))
        self.assertEqual(decision["decision"], EvaluacionIA.DECISION_DESCARTAR)
        self.assertEqual(decision["estado_pipeline"], DetalleEnvio.PIPELINE_DESCARTADA_IA)

    def test_irrelevante_dudoso_va_a_cola(self):
        decision = self._decidir(_salida(relevante=False, rel=0.6))
        self.assertEqual(decision["decision"], EvaluacionIA.DECISION_COLA)

    def test_regla_llm_no_alertar_descarta(self):
        salida = _salida()
        salida["regla_no_alertar"] = "precio_negativo"
        decision = self._decidir(salida)
        self.assertEqual(decision["decision"], EvaluacionIA.DECISION_NO_ALERTAR_REGLA)
        self.assertEqual(decision["estado_pipeline"], DetalleEnvio.PIPELINE_DESCARTADA_IA)

    def test_pais_fuera_de_lista_a_cola(self):
        decision = self._decidir(_salida(pais="ES"))
        self.assertEqual(decision["decision"], EvaluacionIA.DECISION_COLA)

    def test_datos_faltantes_van_a_enriquecer(self):
        self.red.reach = None
        decision = decidir(
            matriz=self.matriz,
            detalle=self.detalle,
            salida=_salida(),
            tipo_alerta="redes",
            alerta={"reach": None, "engagement": 50, "red_social": "twitter"},
        )
        self.assertEqual(decision["estado_pipeline"], DetalleEnvio.PIPELINE_ENRIQUECIENDO)
        self.assertIn("reach", decision["datos_faltantes"])

    def test_nunca_autoenviar_fuerza_cola(self):
        self.matriz.reglas_nunca_autoenviar = [{"tipo": "tonalidad", "valor": "negativo"}]
        decision = self._decidir(_salida())
        self.assertEqual(decision["decision"], EvaluacionIA.DECISION_COLA)
        self.assertTrue(
            any(r.get("regla") == "nunca_autoenviar" for r in decision["reglas_aplicadas"])
        )

    def test_modo_sombra_todo_a_cola(self):
        self.matriz.modo = MatrizCliente.MODO_SOMBRA
        decision = self._decidir(_salida())
        # La decisión de la IA queda registrada pero el estado va a cola
        self.assertEqual(decision["decision"], EvaluacionIA.DECISION_AUTO_ENVIAR)
        self.assertEqual(decision["estado_pipeline"], DetalleEnvio.PIPELINE_COLA_EXCEPCIONES)
