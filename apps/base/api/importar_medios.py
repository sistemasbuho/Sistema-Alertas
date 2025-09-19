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
        # Validación de dominio
        origin = request.headers.get("X-Custom-Domain")
        if origin != "https://api.monitoreo.buho.media/":
            return Response({"error": "Dominio no autorizado"}, status=403)

        proyecto_id = request.data.get("proyecto_id")
        articulos_data = request.data.get("articulos", [])

        if isinstance(proyecto_id, list):
            proyecto_id = proyecto_id[0]

        errores = []
        creados = []

        if not proyecto_id or not articulos_data:
            return Response(
                {"error": "Se requieren 'proyecto_id' y 'articulos'"},
                status=400
            )

        proyecto = Proyecto.objects.filter(id=proyecto_id).first()
        if not proyecto:
            return Response({"error": "Proyecto no encontrado"}, status=404)

        User = get_user_model()
        sistema_user = User.objects.get(id=2) 

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

            # Crear artículo asignando created_by al usuario “sistema”
            articulo = Articulo.objects.create(
                titulo=titulo,
                contenido=contenido,
                url=url.strip(),
                fecha_publicacion=fecha if fecha else now(),
                autor=autor,
                reach=reach,
                proyecto=proyecto,
                created_by=sistema_user
            )

            # Crear detalle de envío
            detalle_envio = DetalleEnvio.objects.create(
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

        # 🔹 Solo si es automático, enviar al API
        if proyecto.tipo_envio == "automatico" and creados:
            enviar_api = EnviarMensajeAPIView()

            simulated_request = HttpRequest()
            simulated_request.method = "POST"
            simulated_request.user = sistema_user
            simulated_request._body = b""
            simulated_request.data = {
                "proyecto_id": proyecto.id,
                "tipo_alerta": "medios",
                "enviar": True,
                "alertas": [
                    {
                        "id": c["id"],
                        "url": c["url"],
                        "contenido": c["titulo"],  # o contenido según prefieras
                        "fecha": str(c["fecha"]),
                        "titulo": c["titulo"],
                        "autor": c.get("autor", ""),
                        "reach": c.get("reach", None)
                    } for c in creados
                ],
            }

            enviar_api.post(simulated_request)

        # 🔹 Respuesta final siempre igual
        return Response(
            {"mensaje": f"{len(creados)} artículos creados.",
             "creados": creados,
             "errores": errores},
            status=201 if creados else 400
        )