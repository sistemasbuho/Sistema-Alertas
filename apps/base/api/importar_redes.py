import json
from rest_framework.views import APIView
from collections.abc import Iterable
from typing import Any, Dict, List, Optional, Tuple

from rest_framework.response import Response
from django.utils import timezone
from apps.proyectos.models import Proyecto
from apps.base.models import Redes,RedesSociales,DetalleEnvio
from apps.whatsapp.api.enviar_mensaje import enviar_alertas_automatico
from django.contrib.auth import get_user_model
from django.http import QueryDict
from apps.base.api.utils import parsear_datetime

class ImportarRedesAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):

        payload = self._extraer_payload(request)
        print("payload recibido:", payload)

        proyecto_id = payload.get("proyecto_id") or payload.get("proyecto")
        redes_data = self._obtener_redes(payload)

        if isinstance(proyecto_id, list):
            proyecto_id = proyecto_id[0]

        errores: List[Dict[str, Any]] = []
        creados: List[Dict[str, Any]] = []

        if not proyecto_id or not redes_data:
            return Response(
                {"error": "Se requieren 'proyecto_id' y 'alertas'"},
                status=400
            )

        proyecto = Proyecto.objects.filter(id=proyecto_id).first()
        if not proyecto:
            return Response({"error": "Proyecto no encontrado"}, status=404)

        
        usuario_creador = self._obtener_usuario_creador(request)

        registros, duplicados_payload = self._normalizar_registros(redes_data)
        errores.extend(duplicados_payload)

        urls = [r[2] for r in registros if r[2]]
        existentes = set(
            Redes.objects.filter(proyecto=proyecto, url__in=urls).values_list("url", flat=True)
        ) if urls else set()

        red_sociales_map = self._mapear_redes_sociales(registros)

        nuevos: List[Redes] = []
        for contenido, fecha_raw, url, autor, reach, engagement, red_social_nombre in registros:
            if url and url in existentes:
                errores.append({"url": url, "error": "La URL ya existe en este proyecto"})
                continue

            red_social_obj = red_sociales_map.get(red_social_nombre)
            nuevos.append(
                Redes(
                    contenido=contenido,
                    fecha_publicacion=self._parse_fecha(fecha_raw),
                    url=url,
                    autor=autor,
                    reach=reach,
                    engagement=engagement,
                    proyecto=proyecto,
                    red_social=red_social_obj,
                    created_by=usuario_creador,
                    modified_by=usuario_creador,
                )
            )

        if nuevos:
            Redes.objects.bulk_create(nuevos, batch_size=300)

            detalles = [
                DetalleEnvio(
                    estado_enviado=False,
                    estado_revisado=True,
                    red_social=red,
                    proyecto_id=proyecto.id,
                    created_by=usuario_creador,
                    modified_by=usuario_creador,
                )
                for red in nuevos
            ]
            DetalleEnvio.objects.bulk_create(detalles, batch_size=300)

            for red in nuevos:
                creados.append({
                    "id": red.id,
                    "url": red.url,
                    "contenido": red.contenido,
                    "autor": red.autor,
                    "fecha": red.fecha_publicacion.isoformat() if red.fecha_publicacion else None,
                    "reach": red.reach,
                    "engagement": red.engagement,
                    "red_social": red.red_social.nombre if red.red_social else None,
                })

        if proyecto.tipo_envio == "automatico" and creados:
            alertas = [
                {
                    "id": c["id"],
                    "url": c["url"],
                    "contenido": c.get("contenido", ""),
                    "titulo": c.get("titulo", ""),
                    "autor": c.get("autor", ""),
                    "fecha": c.get("fecha", ""),
                    "reach": c.get("reach", None),
                    "engagement": c.get("engagement", None),
                    "red_social": c.get("red_social"),
                }
                for c in creados
            ]
            enviar_alertas_automatico(
                proyecto_id=proyecto.id,
                tipo_alerta="redes",
                alertas=alertas,
                usuario_id=getattr(usuario_creador, "id", None)
            )

        
        return Response(
            {
                "mensaje": f"{len(creados)} publicaciones creadas.",
                "creados": creados,
                "errores": errores
            },
            status=201 if creados else 400
        )

    def _parse_fecha(self, fecha_raw):
        fecha = parsear_datetime(fecha_raw)
        return fecha or timezone.now()

    def _normalizar_registros(
        self, redes_data: List[Dict[str, Any]]
    ) -> Tuple[
        List[Tuple[Optional[str], Any, str, Optional[str], Any, Any, Optional[str]]],
        List[Dict[str, Any]],
    ]:
        registros = []
        errores = []
        vistos = set()

        for data in redes_data:
            contenido = data.get("contenido")
            fecha_raw = data.get("fecha")
            url = (data.get("url") or "").strip()
            autor = data.get("autor")
            reach = data.get("reach")
            engagement = data.get("engagement")
            red_social_nombre = data.get("red_social")

            if url:
                if url in vistos:
                    errores.append({"url": url, "error": "URL duplicada en el payload"})
                    continue
                vistos.add(url)

            registros.append(
                (contenido, fecha_raw, url, autor, reach, engagement, red_social_nombre)
            )

        return registros, errores

    def _mapear_redes_sociales(
        self,
        registros: List[Tuple[Optional[str], Any, str, Optional[str], Any, Any, Optional[str]]],
    ) -> Dict[Optional[str], Optional[RedesSociales]]:
        nombres = {r[6] for r in registros if r[6]}
        if not nombres:
            return {}
        mapa = {
            rs.nombre: rs
            for rs in RedesSociales.objects.filter(nombre__in=nombres)
        }
        return mapa

    def _extraer_payload(self, request) -> Dict[str, Any]:
        data: Any = request.data

        if isinstance(data, QueryDict):
            data = {
                key: [self._parse_value(v) for v in values] if len(values) > 1 else self._parse_value(values[0])
                for key, values in data.lists()
            }

        if data:
            return data

        body = request.body
        if not body:
            return {}

        if isinstance(body, bytes):
            try:
                body = body.decode("utf-8")
            except UnicodeDecodeError:
                return {}

        try:
            parsed = json.loads(body)
        except (TypeError, json.JSONDecodeError):
            return {}

        parsed = self._parse_value(parsed)

        if isinstance(parsed, list):
            return {"alertas": parsed}
        if isinstance(parsed, dict):
            return parsed

        return {}

    def _obtener_redes(self, data: Any) -> List[Dict[str, Any]]:
        if hasattr(data, "getlist"):
            redes = data.getlist("redes") or []
        else:
            redes = data.get("redes", [])

        alertas = data.get("alertas") if isinstance(data, dict) else data.get("alertas", [])

        if alertas:
            if isinstance(alertas, dict):
                alertas_iterable: Iterable = [alertas]
            else:
                alertas_iterable = alertas if isinstance(alertas, Iterable) and not isinstance(alertas, (str, bytes)) else [alertas]
            redes = [self._map_alerta_to_red(alerta) for alerta in alertas_iterable]

        if isinstance(redes, dict):
            redes = [redes]

        return list(redes)

    def _obtener_usuario_creador(self, request):
        UserModel = get_user_model()

        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            return user

        posibles_fuentes = []
        if hasattr(request, "data"):
            posibles_fuentes.append(request.data)
        if hasattr(request, "query_params"):
            posibles_fuentes.append(request.query_params)

        for fuente in posibles_fuentes:
            if not hasattr(fuente, "get"):
                continue
            for clave in ("usuario_id", "usuario", "user_id", "created_by"):
                valor = fuente.get(clave)
                if isinstance(valor, list):
                    valor = valor[0]
                if not valor:
                    continue
                try:
                    return UserModel.objects.get(id=valor)
                except (UserModel.DoesNotExist, ValueError, TypeError):
                    continue

        return UserModel.objects.get(id=2)

    def _map_alerta_to_red(self, alerta: Dict[str, Any]) -> Dict[str, Any]:
        reach = alerta.get("reach")
        if reach is None:
            reach = alerta.get("alcance")

        engagement = alerta.get("engagement")
        if engagement is None:
            engagement = alerta.get("engammet")
        if engagement is None:
            engagement = alerta.get("engagement_rate")

        return {
            "contenido": alerta.get("contenido") or alerta.get("content"),
            "fecha": alerta.get("fecha") or alerta.get("published"),
            "url": alerta.get("url") or alerta.get("link"),
            "autor": alerta.get("autor") or alerta.get("autor_name"),
            "reach": reach,
            "engagement": engagement,
            "red_social": alerta.get("red_social") or alerta.get("social_network") or alerta.get("SOCIAL_NETWORK"),
        }

    def _parse_value(self, value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value

        if isinstance(value, (bytes, bytearray)):
            try:
                value = value.decode("utf-8")
            except UnicodeDecodeError:
                return value

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return value
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value

        return value
