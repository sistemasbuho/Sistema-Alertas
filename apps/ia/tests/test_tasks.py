from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.base.models import DetalleEnvio, Redes, RedesSociales
from apps.ia.models import EvaluacionIA, MatrizCliente
from apps.ia.services.vertex import MetadatosLLM
from apps.ia.tasks import clasificar_alerta, rescatar_alertas_atascadas
from apps.proyectos.models import Proyecto

SALIDA_AUTO = {
    "relevante": True,
    "relevancia_score": 0.95,
    "tonalidad": "negativo",
    "tonalidad_score": 0.92,
    "categoria_sector": "belleza",
    "pais": "PE",
    "pais_score": 0.9,
    "regla_no_alertar": None,
    "marca_detectada": "Garnier",
    "razones": ["queja por daño de producto"],
}

META = MetadatosLLM(modelo="gemini-test", latencia_ms=100, tokens_entrada=10, tokens_salida=5)


def _mk_pipeline(modo=MatrizCliente.MODO_ACTIVO, activo=True):
    proyecto = Proyecto.objects.create(
        nombre="LOREAL", codigo_acceso="g@g.us", tipo_alerta="redes"
    )
    matriz = MatrizCliente.objects.create(
        proyecto=proyecto,
        activo=activo,
        modo=modo,
        paises=["PE", "CO"],
        umbral_confianza={"redes": {"auto_envio": 0.85, "descarte": 0.90}},
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
    red = Redes.objects.create(
        contenido="Garnier me dañó el pelo",
        fecha_publicacion=timezone.now(),
        url="https://twitter.com/u/status/9",
        autor="@u",
        reach=2000,
        engagement=50,
        red_social=RedesSociales.objects.create(nombre="Twitter"),
        proyecto=proyecto,
    )
    detalle = DetalleEnvio.objects.create(
        proyecto=proyecto,
        red_social=red,
        estado_pipeline=DetalleEnvio.PIPELINE_PENDIENTE_IA,
    )
    return proyecto, matriz, detalle


class ClasificarAlertaTaskTests(TestCase):
    @patch("apps.whatsapp.tasks.enviar_alerta.delay")
    @patch("apps.ia.services.vertex.clasificar", return_value=(SALIDA_AUTO, META))
    def test_flujo_auto_aprobada_encadena_envio(self, mock_llm, mock_envio):
        _, _, detalle = _mk_pipeline()
        resultado = clasificar_alerta.apply(args=[str(detalle.id)]).get()

        detalle.refresh_from_db()
        self.assertEqual(resultado, DetalleEnvio.PIPELINE_AUTO_APROBADA)
        self.assertEqual(detalle.estado_pipeline, DetalleEnvio.PIPELINE_AUTO_APROBADA)
        mock_envio.assert_called_once_with(str(detalle.id))

        evaluacion = EvaluacionIA.objects.get(detalle_envio=detalle)
        self.assertEqual(evaluacion.decision, EvaluacionIA.DECISION_AUTO_ENVIAR)
        self.assertEqual(evaluacion.modelo, "gemini-test")
        self.assertAlmostEqual(evaluacion.confianza_global, 0.9)
        self.assertEqual(evaluacion.riesgo, "bajo")

    @patch("apps.whatsapp.tasks.enviar_alerta.delay")
    @patch("apps.ia.services.vertex.clasificar", return_value=(SALIDA_AUTO, META))
    def test_modo_sombra_va_a_cola_sin_envio(self, mock_llm, mock_envio):
        _, _, detalle = _mk_pipeline(modo=MatrizCliente.MODO_SOMBRA)
        clasificar_alerta.apply(args=[str(detalle.id)])

        detalle.refresh_from_db()
        self.assertEqual(detalle.estado_pipeline, DetalleEnvio.PIPELINE_COLA_EXCEPCIONES)
        self.assertFalse(detalle.estado_revisado)
        mock_envio.assert_not_called()
        # La decisión de la IA quedó registrada para calibración
        evaluacion = EvaluacionIA.objects.get(detalle_envio=detalle)
        self.assertEqual(evaluacion.decision, EvaluacionIA.DECISION_AUTO_ENVIAR)

    @patch("apps.ia.services.vertex.clasificar", side_effect=RuntimeError("LLM caído"))
    def test_error_llm_cae_a_cola_humana(self, mock_llm):
        _, _, detalle = _mk_pipeline()
        clasificar_alerta.apply(args=[str(detalle.id)])

        detalle.refresh_from_db()
        self.assertEqual(detalle.estado_pipeline, DetalleEnvio.PIPELINE_COLA_EXCEPCIONES)
        evaluacion = EvaluacionIA.objects.filter(detalle_envio=detalle).latest("created_at")
        self.assertEqual(evaluacion.decision_por, EvaluacionIA.POR_ERROR)
        self.assertEqual(evaluacion.estado, EvaluacionIA.ESTADO_ERROR)

    @patch("apps.ia.services.vertex.clasificar", return_value=(SALIDA_AUTO, META))
    def test_idempotencia_estado_ya_resuelto_se_omite(self, mock_llm):
        _, _, detalle = _mk_pipeline()
        detalle.estado_pipeline = DetalleEnvio.PIPELINE_ENVIADA
        detalle.save()
        resultado = clasificar_alerta.apply(args=[str(detalle.id)]).get()
        self.assertEqual(resultado, "omitida")
        mock_llm.assert_not_called()

    def test_sin_matriz_vuelve_a_manual(self):
        _, matriz, detalle = _mk_pipeline(activo=False)
        resultado = clasificar_alerta.apply(args=[str(detalle.id)]).get()
        detalle.refresh_from_db()
        self.assertEqual(resultado, "sin_matriz")
        self.assertEqual(detalle.estado_pipeline, DetalleEnvio.PIPELINE_MANUAL)


class SweeperTests(TestCase):
    def test_atascada_pasa_a_cola(self):
        _, _, detalle = _mk_pipeline()
        detalle.estado_pipeline = DetalleEnvio.PIPELINE_CLASIFICANDO
        detalle.save()
        # forzar antigüedad más allá del timeout total
        DetalleEnvio.objects.filter(id=detalle.id).update(
            modified_at=timezone.now() - timedelta(seconds=999)
        )

        rescatadas = rescatar_alertas_atascadas.apply().get()

        self.assertEqual(rescatadas, 1)
        detalle.refresh_from_db()
        self.assertEqual(detalle.estado_pipeline, DetalleEnvio.PIPELINE_COLA_EXCEPCIONES)
        evaluacion = EvaluacionIA.objects.get(detalle_envio=detalle)
        self.assertEqual(evaluacion.decision_por, EvaluacionIA.POR_TIMEOUT)

    def test_reciente_no_se_toca(self):
        _, _, detalle = _mk_pipeline()
        detalle.estado_pipeline = DetalleEnvio.PIPELINE_CLASIFICANDO
        detalle.save()
        rescatadas = rescatar_alertas_atascadas.apply().get()
        self.assertEqual(rescatadas, 0)
