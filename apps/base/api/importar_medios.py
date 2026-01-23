from collections.abc import Iterable
from typing import Any, Dict, List, Optional, Tuple

from rest_framework.response import Response
from apps.base.models import Articulo, DetalleEnvio
from apps.proyectos.models import Proyecto
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from apps.whatsapp.api.enviar_mensaje import enviar_alertas_automatico
from django.utils import timezone
from apps.base.api.utils import parsear_datetime


class ImportarArticuloAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        print("✅ Llegó a ImportarArticuloAPIView")
        print("request.data:", request.data)
        print("request.FILES:", request.FILES)

        proyecto_id = request.data.get("proyecto_id") or request.data.get("proyecto")
        articulos_data = self._obtener_articulos(request.data)

        if isinstance(proyecto_id, list):
            proyecto_id = proyecto_id[0]

        errores: List[Dict[str, Any]] = []
        creados: List[Dict[str, Any]] = []

        if not proyecto_id or not articulos_data:
            return Response(
                {"error": "Se requieren 'proyecto_id' y 'alertas'"},
                status=400
            )

        proyecto = Proyecto.objects.filter(id=proyecto_id).first()
        if not proyecto:
            return Response({"error": "Proyecto no encontrado"}, status=404)

        usuario_creador = self._obtener_usuario_creador(request)
        print('lega aqui')

        registros, duplicados_payload = self._normalizar_registros(articulos_data)
        errores.extend(duplicados_payload)

        urls = [r[3] for r in registros if r[3]]
        existentes = set(
            Articulo.objects.filter(proyecto=proyecto, url__in=urls).values_list("url", flat=True)
        ) if urls else set()

        nuevos: List[Articulo] = []
        aceptados: List[Tuple[Optional[str], Optional[str], Any, str, Optional[str], Any, Any]] = []
        for titulo, contenido, fecha_raw, url, autor, reach, engagement in registros:
            if url and url in existentes:
                errores.append({"url": url, "error": "La URL ya existe en este proyecto"})
                continue

            nuevos.append(
                Articulo(
                    titulo=titulo,
                    contenido=contenido,
                    url=url,
                    fecha_publicacion=self._parse_fecha(fecha_raw),
                    autor=autor,
                    reach=reach,
                    proyecto=proyecto,
                    created_by=usuario_creador,
                    modified_by=usuario_creador,
                )
            )
            aceptados.append((titulo, contenido, fecha_raw, url, autor, reach, engagement))

        if nuevos:
            Articulo.objects.bulk_create(nuevos, batch_size=300)

            detalles = [
                DetalleEnvio(
                    estado_enviado=False,
                    estado_revisado=True,
                    medio=articulo,
                    proyecto_id=proyecto.id,
                    created_by=usuario_creador,
                    modified_by=usuario_creador,
                )
                for articulo in nuevos
            ]
            DetalleEnvio.objects.bulk_create(detalles, batch_size=300)

            for articulo, registro in zip(nuevos, aceptados):
                engagement = registro[6]
                creados.append({
                    "id": articulo.id,
                    "titulo": articulo.titulo,
                    "url": articulo.url,
                    "contenido": articulo.contenido,
                    "autor": articulo.autor,
                    "fecha": articulo.fecha_publicacion.isoformat() if articulo.fecha_publicacion else None,
                    "reach": articulo.reach,
                    "engagement": engagement,
                })

        if proyecto.tipo_envio == "automatico" and creados:
            alertas = [
                {
                    "id": c["id"],
                    "url": c["url"],
                    "contenido": c.get("contenido") or c.get("titulo"),
                    "titulo": c.get("titulo"),
                    "autor": c.get("autor"),
                    "fecha": c.get("fecha"),
                    "reach": c.get("reach"),
                    "engagement": c.get("engagement"),
                }
                for c in creados
            ]
            enviar_alertas_automatico(
                proyecto_id=proyecto.id,
                tipo_alerta="medios",
                alertas=alertas,
                usuario_id=getattr(usuario_creador, "id", None)
            )
        print('creados--------------',creados)

        return Response(
            {
                "mensaje": f"{len(creados)} artículos creados.",
                "creados": creados,
                "errores": errores
            },
            status=201 if creados else 400
        )

    def _obtener_articulos(self, data: Any) -> List[Dict[str, Any]]:
        if hasattr(data, "getlist"):
            articulos = data.getlist("articulos") or []
        else:
            articulos = data.get("articulos", [])

        alertas = data.get("alertas") if isinstance(data, dict) else data.get("alertas", [])

        if alertas:
            alertas_iterable: Iterable = alertas if isinstance(alertas, Iterable) and not isinstance(alertas, (str, bytes, dict)) else [alertas]
            if isinstance(alertas, dict):
                alertas_iterable = [alertas]
            articulos = [self._map_alerta_to_articulo(alerta) for alerta in alertas_iterable]

        if isinstance(articulos, dict):
            articulos = [articulos]

        return list(articulos)

    def _parse_fecha(self, fecha_raw):
        fecha = parsear_datetime(fecha_raw)
        return fecha or timezone.now()

    def _normalizar_registros(
        self, articulos_data: List[Dict[str, Any]]
    ) -> Tuple[
        List[Tuple[Optional[str], Optional[str], Any, str, Optional[str], Any, Any]],
        List[Dict[str, Any]],
    ]:
        registros = []
        errores = []
        vistos = set()

        for data in articulos_data:
            titulo = data.get("titulo")
            contenido = data.get("contenido")
            fecha_raw = data.get("fecha")
            url = (data.get("url") or "").strip()
            autor = data.get("autor")
            reach = data.get("reach")
            engagement = data.get("engagement")

            if url:
                if url in vistos:
                    errores.append({"url": url, "error": "URL duplicada en el payload"})
                    continue
                vistos.add(url)

            registros.append((titulo, contenido, fecha_raw, url, autor, reach, engagement))

        return registros, errores

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

    def _map_alerta_to_articulo(self, alerta: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "titulo": alerta.get("titulo") or alerta.get("title"),
            "contenido": alerta.get("contenido") or alerta.get("content"),
            "fecha": alerta.get("fecha") or alerta.get("published"),
            "url": alerta.get("url") or alerta.get("link"),
            "autor": alerta.get("autor") or alerta.get("autor_name"),
            "reach": alerta.get("reach"),
            "engagement": alerta.get("engagement") or alerta.get("engagement_rate"),
        }
