from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.base.models import Articulo,Redes,DetalleEnvio
from apps.proyectos.models import Proyecto
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.whatsapp.api.enviar_mensaje import EnviarMensajeAPIView




from django.utils.timezone import now


class ImportarArticuloAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        origin = request.headers.get("X-Custom-Domain")
        if origin != "https://api.monitoreo.buho.media/":
            return Response({"error": "Dominio no autorizado"}, status=403)



        proyecto_id = request.data.get("proyecto_id")
        articulos_data = request.data.get("articulos", [])

        if isinstance(proyecto_id, list):
            proyecto_id = proyecto_id[0]

        if not proyecto_id or not articulos_data:
            return Response({"error": "Se requieren 'proyecto_id' y 'articulos'"}, status=403)

        proyecto = Proyecto.objects.filter(id=proyecto_id).first()
        if not proyecto:
            return Response({"error": "Proyecto no encontrado"}, status=404)

        # 🔹 Recuperamos el system_user
        User = get_user_model()
        system_user = User.objects.get(id=2)

        creados, errores = [], []

        for data in articulos_data:
            titulo = data.get("titulo")
            contenido = data.get("contenido")
            fecha = data.get("fecha")
            url = data.get("url")
            autor = data.get("autor")
            reach = data.get("reach")

            if not url or not url.strip():
                errores.append({"titulo": titulo, "error": "La URL es obligatoria"})
                continue

            if Articulo.objects.filter(url=url, proyecto=proyecto).exists():
                errores.append({"url": url, "error": "La URL ya existe en este proyecto"})
                continue

            # Crear artículo asignando created_by al system_user
            articulo = Articulo.objects.create(
                titulo=titulo,
                contenido=contenido,
                url=url.strip(),
                fecha_publicacion=fecha if fecha else now(),
                autor=autor,
                reach=reach,
                proyecto=proyecto,
                created_by=system_user
            )

            # Crear detalle de envío
            DetalleEnvio.objects.create(
                estado_enviado=False,
                estado_revisado=False,
                medio=articulo,
                proyecto_id=proyecto.id
            )

            creados.append({
                "id": articulo.id,
                "titulo": articulo.titulo,
                "url": articulo.url
            })

        print('PASA QAUI')
        print('PASA QAUI',proyecto.tipo_envio)

        if proyecto.tipo_envio == "automatico" and creados:
            enviar_api = EnviarMensajeAPIView()

            # Simulamos un request para pasar los datos correctamente
            simulated_request = HttpRequest()
            simulated_request.method = "POST"
            simulated_request.user = system_user
            simulated_request._body = b""  # requerido por DRF internamente
            simulated_request.data = {
                "proyecto_id": proyecto.id,
                "tipo_alerta": "medios",
                "alertas": [
                    {"id": c["id"], "url": c["url"], "contenido": c["titulo"]}
                    for c in creados
                ],
            }

            enviar_api.post(simulated_request)

        return Response(
            {
                "mensaje": f"{len(creados)} artículos creados.",
                "creados": creados,
                "errores": errores
            },
            status=201 if creados else 400
        )