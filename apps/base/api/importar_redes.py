import json
from rest_framework.views import APIView
from collections.abc import Iterable
from typing import Any, Dict, List

from rest_framework.response import Response
from django.utils.timezone import now
from apps.proyectos.models import Proyecto
from apps.base.models import Redes,RedesSociales,DetalleEnvio
from apps.whatsapp.api.enviar_mensaje import enviar_alertas_automatico
from django.contrib.auth import get_user_model
from django.http import QueryDict

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

        errores = []
        creados = []

        if not proyecto_id or not redes_data:
            return Response(
                {"error": "Se requieren 'proyecto_id' y 'alertas'"},
                status=400
            )

        proyecto = Proyecto.objects.filter(id=proyecto_id).first()
        if not proyecto:
            return Response({"error": "Proyecto no encontrado"}, status=404)

        
        User = get_user_model()
        sistema_user = User.objects.get(id=2) 

        for data in redes_data:
            contenido = data.get("contenido")
            fecha = data.get("fecha")
            url = (data.get("url") or "").strip()
            autor = data.get("autor")
            reach = data.get("reach")
            engagement = data.get("engagement")
            red_social_nombre = data.get("red_social")

            if url and Redes.objects.filter(url=url, proyecto=proyecto).exists():
                errores.append({
                    "url": url,
                    "error": "La URL ya existe en este proyecto"
                })
                continue
            
            red_social_obj = None
            if red_social_nombre:
                red_social_obj = RedesSociales.objects.filter(nombre=red_social_nombre).first()


            red = Redes.objects.create(
                contenido=contenido,
                fecha_publicacion=fecha if fecha else now(),
                url=url,
                autor=autor,
                reach=reach,
                engagement=engagement,
                proyecto=proyecto,
                red_social=red_social_obj 
            )

            detalle_envio = DetalleEnvio.objects.create(
                estado_enviado=False,
                estado_revisado=False,
                red_social=red,
                proyecto_id=proyecto.id 
            )

            creados.append({
                "id": red.id,
                "url": red.url,
                "contenido": red.contenido,
                "autor": red.autor,
                "fecha": red.fecha_publicacion.isoformat() if red.fecha_publicacion else None,
                "reach": red.reach,
                "engagement": red.engagement,
                "red_social": red_social_nombre,
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
                usuario_id=sistema_user.id
            )

        
        return Response(
            {
                "mensaje": f"{len(creados)} publicaciones creadas.",
                "creados": creados,
                "errores": errores
            },
            status=201 if creados else 400
        )

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

    def _map_alerta_to_red(self, alerta: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "contenido": alerta.get("contenido") or alerta.get("content"),
            "fecha": alerta.get("fecha") or alerta.get("published"),
            "url": alerta.get("url") or alerta.get("link"),
            "autor": alerta.get("autor") or alerta.get("autor_name"),
            "reach": alerta.get("reach") or alerta.get("alcance"),
            "engagement": alerta.get("engagement") or alerta.get("engammet") or alerta.get("engagement_rate"),
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


