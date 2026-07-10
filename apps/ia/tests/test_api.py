from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.base.models import DetalleEnvio, Redes, RedesSociales
from apps.ia.models import EvaluacionIA, MatrizCliente
from apps.proyectos.models import Proyecto


def _mk_cola(proyecto=None, contenido="Garnier dañó mi piel"):
    proyecto = proyecto or Proyecto.objects.create(
        nombre="LOREAL", codigo_acceso="g@g.us", tipo_alerta="redes"
    )
    red = Redes.objects.create(
        contenido=contenido,
        fecha_publicacion=timezone.now(),
        url=f"https://twitter.com/u/status/{timezone.now().timestamp()}",
        autor="@u",
        reach=2000,
        engagement=50,
        red_social=RedesSociales.objects.create(nombre="Twitter"),
        proyecto=proyecto,
    )
    detalle = DetalleEnvio.objects.create(
        proyecto=proyecto,
        red_social=red,
        estado_pipeline=DetalleEnvio.PIPELINE_COLA_EXCEPCIONES,
        estado_revisado=False,
    )
    evaluacion = EvaluacionIA.objects.create(
        detalle_envio=detalle,
        proyecto=proyecto,
        tipo_alerta="redes",
        estado=EvaluacionIA.ESTADO_COMPLETADA,
        relevante=True,
        relevancia_score=0.7,
        tonalidad="negativo",
        tonalidad_score=0.6,
        confianza_global=0.6,
        pais_detectado="PE",
        categoria_sector="belleza",
        riesgo="medio",
        decision=EvaluacionIA.DECISION_COLA,
        decision_por=EvaluacionIA.POR_IA,
        razones=["confianza bajo umbral"],
    )
    return proyecto, detalle, evaluacion


class ColaExcepcionesAPITests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user("analista", password="x")
        self.client.force_authenticate(user)
        self.user = user

    def test_lista_incluye_sugerencias_ia(self):
        proyecto, detalle, _ = _mk_cola()
        respuesta = self.client.get("/api/ia/cola-excepciones/")
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos["count"], 1)
        item = datos["results"][0]
        self.assertEqual(item["id"], str(detalle.id))
        self.assertEqual(item["tipo"], "redes")
        self.assertEqual(item["evaluacion_ia"]["tonalidad"], "negativo")
        self.assertEqual(item["evaluacion_ia"]["confianza_global"], 0.6)
        self.assertIn("razones", item["evaluacion_ia"])
        self.assertIn("mensaje_formateado", item)

    def test_resumen(self):
        _mk_cola()
        respuesta = self.client.get("/api/ia/cola-excepciones/resumen/")
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos["pendientes"], 1)
        self.assertEqual(datos["por_proyecto"][0]["pendientes"], 1)

    @patch("apps.whatsapp.tasks.enviar_alerta.delay")
    def test_confirmar_y_enviar(self, mock_envio):
        _, detalle, evaluacion = _mk_cola()
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(
                f"/api/ia/cola-excepciones/{detalle.id}/resolver/",
                {"accion": "confirmar", "enviar": True},
                format="json",
            )
        self.assertEqual(respuesta.status_code, 200)
        detalle.refresh_from_db()
        evaluacion.refresh_from_db()
        self.assertEqual(detalle.estado_pipeline, DetalleEnvio.PIPELINE_APROBADA_HUMANA)
        self.assertTrue(detalle.estado_revisado)
        self.assertEqual(evaluacion.revision_humana, EvaluacionIA.REVISION_CONFIRMADA)
        self.assertEqual(evaluacion.revisado_por, self.user)
        mock_envio.assert_called_once_with(str(detalle.id))

    @patch("apps.whatsapp.tasks.enviar_alerta.delay")
    def test_corregir_guarda_diff_y_aplica_campos(self, mock_envio):
        _, detalle, evaluacion = _mk_cola()
        respuesta = self.client.post(
            f"/api/ia/cola-excepciones/{detalle.id}/resolver/",
            {
                "accion": "corregir",
                "enviar": False,
                "correccion": {"tonalidad": "neutral", "pais": "PE"},
                "campos": {"reach": 5000},
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200)
        evaluacion.refresh_from_db()
        detalle.refresh_from_db()
        # Solo lo que cambió respecto a la IA queda en el diff
        self.assertEqual(evaluacion.correccion["tonalidad"], "neutral")
        self.assertNotIn("pais", evaluacion.correccion)
        self.assertEqual(evaluacion.correccion["campos"]["reach"], 5000)
        self.assertEqual(evaluacion.revision_humana, EvaluacionIA.REVISION_CORREGIDA)
        detalle.red_social.refresh_from_db()
        self.assertEqual(detalle.red_social.reach, 5000)
        mock_envio.assert_not_called()

    def test_descartar(self):
        _, detalle, evaluacion = _mk_cola()
        respuesta = self.client.post(
            f"/api/ia/cola-excepciones/{detalle.id}/resolver/",
            {"accion": "descartar", "motivo": "hashtag colisión"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200)
        detalle.refresh_from_db()
        evaluacion.refresh_from_db()
        self.assertEqual(detalle.estado_pipeline, DetalleEnvio.PIPELINE_DESCARTADA_HUMANA)
        self.assertEqual(evaluacion.revision_humana, EvaluacionIA.REVISION_RECHAZADA)
        self.assertEqual(evaluacion.comentario_revision, "hashtag colisión")

    def test_resolver_dos_veces_da_409(self):
        _, detalle, _ = _mk_cola()
        self.client.post(
            f"/api/ia/cola-excepciones/{detalle.id}/resolver/",
            {"accion": "descartar"},
            format="json",
        )
        respuesta = self.client.post(
            f"/api/ia/cola-excepciones/{detalle.id}/resolver/",
            {"accion": "confirmar"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 409)

    def test_bulk_exige_mismo_proyecto(self):
        _, detalle1, _ = _mk_cola()
        _, detalle2, _ = _mk_cola()  # otro proyecto
        respuesta = self.client.post(
            "/api/ia/cola-excepciones/resolver-bulk/",
            {"ids": [str(detalle1.id), str(detalle2.id)], "accion": "confirmar"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 400)

    @patch("apps.whatsapp.tasks.enviar_alerta.delay")
    def test_bulk_confirmar(self, mock_envio):
        proyecto, detalle1, _ = _mk_cola()
        _, detalle2, _ = _mk_cola(proyecto=proyecto)
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(
                "/api/ia/cola-excepciones/resolver-bulk/",
                {"ids": [str(detalle1.id), str(detalle2.id)], "accion": "confirmar", "enviar": True},
                format="json",
            )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.json()["procesadas"]), 2)
        self.assertEqual(mock_envio.call_count, 2)


class MatrizAPITests(APITestCase):
    def setUp(self):
        self.client.force_authenticate(get_user_model().objects.create_user("u", password="x"))
        self.proyecto = Proyecto.objects.create(
            nombre="LOREAL", codigo_acceso="g@g.us", tipo_alerta="redes"
        )

    def test_get_sin_matriz_devuelve_default(self):
        respuesta = self.client.get(f"/api/ia/matriz/{self.proyecto.id}/")
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos["proyecto"], str(self.proyecto.id))
        self.assertFalse(datos["activo"])
        self.assertEqual(datos["marcas"], [])
        self.assertFalse(MatrizCliente.objects.exists())

    def test_put_crea_y_actualiza(self):
        payload = {
            "activo": True,
            "modo": "sombra",
            "marcas": ["Garnier", "Elvive"],
            "paises": ["PE", "CO"],
            "umbral_confianza": {"redes": {"auto_envio": 0.9, "descarte": 0.95}},
        }
        respuesta = self.client.put(
            f"/api/ia/matriz/{self.proyecto.id}/", payload, format="json"
        )
        self.assertEqual(respuesta.status_code, 201)
        matriz = MatrizCliente.objects.get(proyecto=self.proyecto)
        self.assertEqual(matriz.marcas, ["Garnier", "Elvive"])

        respuesta = self.client.put(
            f"/api/ia/matriz/{self.proyecto.id}/", {"marcas": ["NYX"]}, format="json"
        )
        self.assertEqual(respuesta.status_code, 200)
        matriz.refresh_from_db()
        self.assertEqual(matriz.marcas, ["NYX"])
        self.assertEqual(matriz.paises, ["PE", "CO"])  # partial update


class AuditoriaYMetricasAPITests(APITestCase):
    def setUp(self):
        self.client.force_authenticate(get_user_model().objects.create_user("u", password="x"))

    def test_evaluaciones_lista_y_detalle(self):
        _, _, evaluacion = _mk_cola()
        respuesta = self.client.get("/api/ia/evaluaciones/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["count"], 1)

        detalle = self.client.get(f"/api/ia/evaluaciones/{evaluacion.id}/")
        self.assertEqual(detalle.status_code, 200)
        datos = detalle.json()
        self.assertIn("reglas_aplicadas", datos)
        self.assertIn("snapshot_matriz", datos)

    def test_metricas_buckets(self):
        _, _, evaluacion = _mk_cola()
        evaluacion.revision_humana = EvaluacionIA.REVISION_CONFIRMADA
        evaluacion.save()
        respuesta = self.client.get("/api/ia/metricas/")
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos["total_evaluaciones"], 1)
        bucket = datos["confianza_buckets"][0]
        self.assertEqual(bucket["bucket"], "0.6-0.7")
        self.assertEqual(bucket["tasa_confirmacion"], 1.0)
