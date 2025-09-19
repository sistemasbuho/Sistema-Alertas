from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.timezone import now
from apps.proyectos.models import Proyecto
from apps.base.models import Redes,RedesSociales,DetalleEnvio

class ImportarRedesAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        # Validación de dominio si es necesario
        origin = request.headers.get("X-Custom-Domain")
        if origin != "https://api.monitoreo.buho.media/":
            return Response({"error": "Dominio no autorizado"}, status=403)

        proyecto_id = request.data.get("proyecto_id")
        redes_data = request.data.get("redes", [])

        if isinstance(proyecto_id, list):
            proyecto_id = proyecto_id[0]

        errores = []
        creados = []

        if not proyecto_id or not redes_data:
            return Response(
                {"error": "Se requieren 'proyecto_id' y 'redes'"},
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
            url = data.get("url")
            autor = data.get("autor")
            reach = data.get("reach")
            engagement = data.get("engagement")
            red_social_nombre = data.get("red_social")

            if not url or not url.strip():
                errores.append({
                    "contenido": contenido,
                    "error": "La URL es obligatoria"
                })
                continue

            if Redes.objects.filter(url=url, proyecto=proyecto).exists():
                errores.append({
                    "url": url,
                    "error": "La URL ya existe en este proyecto"
                })
                continue

            # Buscar red social si viene en el payload
            red_social_obj = None
            if red_social_nombre:
                red_social_obj = RedesSociales.objects.filter(nombre=red_social_nombre).first()

            # Crear publicación en redes
            red = Redes.objects.create(
                contenido=contenido,
                fecha_publicacion=fecha if fecha else now(),
                url=url.strip(),
                autor=autor,
                reach=reach,
                engagement=engagement,
                proyecto=proyecto,
                red_social=red_social_obj,
                created_by=sistema_user
            )

            # Crear detalle de envío
            detalle_envio = DetalleEnvio.objects.create(
                estado_enviado=False,
                estado_revisado=False,
                red_social=red,
                proyecto_id=proyecto.id
            )

            creados.append({
                "id": red.id,
                "url": red.url,
                "fecha": red.fecha_publicacion,
                "autor": autor,
                "contenido": contenido,
                "reach": reach,
                "engagement": engagement,
            })

        envio_resultado = None

        if proyecto.tipo_envio == "automatico" and creados:
            # Llamar al mismo flujo de envío automático
            enviar_api = EnviarMensajeAPIView()
            fake_request = request._request  # HttpRequest base
            fake_request.data = {
                "proyecto_id": str(proyecto.id),
                "tipo_alerta": "redes",
                "alertas": creados
            }
            envio_resultado = enviar_api.post(request=fake_request).data

        elif proyecto.tipo_envio == "programado" and creados:
            for creado in creados:
                DetalleEnvio.objects.filter(red_social_id=creado["id"]).update(
                    fecha_programada=timezone.now() + timedelta(hours=12)
                )
            envio_resultado = {
                "estado": "programado",
                "detalle": f"Se programaron {len(creados)} publicaciones para envío"
            }

        return Response(
            {
                "mensaje": f"{len(creados)} publicaciones creadas.",
                "creados": creados,
                "errores": errores,
                "envio": envio_resultado if envio_resultado else "no_aplica"
            },
            status=201 if creados else 400
        )


