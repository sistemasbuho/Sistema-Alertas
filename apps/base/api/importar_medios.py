from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.base.models import Articulo,Redes,DetalleEnvio
from apps.proyectos.models import Proyecto
from rest_framework.views import APIView
from django.contrib.auth import get_user_model



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
            return Response({"error": "Se requieren 'proyecto_id' y 'articulos'"},
                            status=400)

        proyecto = Proyecto.objects.filter(id=proyecto_id).first()
        if not proyecto:
            return Response({"error": "Proyecto no encontrado"}, status=404)

        # obtener/crear usuario sistema (no dependemos de id fijo para no romper si cambian)
        User = get_user_model()
        sistema_user = User.objects.filter(id=2).first()
        if not sistema_user:
            sistema_user, _ = User.objects.get_or_create(
                username="sistema",
                defaults={"email": "sistema@buho.media", "first_name": "Sistema"}
            )

        # Usamos siempre el usuario de sistema (no hay autenticación para estas peticiones)
        usuario_envio = sistema_user

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

            articulo = Articulo.objects.create(
                titulo=titulo,
                contenido=contenido,
                url=url.strip(),
                fecha_publicacion=fecha if fecha else now(),
                autor=autor,
                reach=reach,
                proyecto=proyecto,
                created_by=usuario_envio
            )

            detalle_envio = DetalleEnvio.objects.create(
                estado_enviado=False,
                estado_revisado=False,
                medio=articulo,
                proyecto_id=proyecto.id,
                usuario=usuario_envio
            )

            creados.append({
                "id": articulo.id,
                "titulo": articulo.titulo,
                "url": articulo.url
            })

        envio_resultado = None

        # Si es automático enviamos UNA sola vez y con solo los IDs en 'alertas'
        if proyecto.tipo_envio == "automatico" and creados:
            enviar_api = EnviarMensajeAPIView()
            fake_request = request._request  # HttpRequest subyacente
            fake_request.user = usuario_envio  # evita que el logger lea 'AnonymousUser'
            fake_request.data = {
                "proyecto_id": str(proyecto.id),
                "tipo_alerta": "medios",
                "alertas": [{"id": c["id"]} for c in creados],
            }
            envio_resultado = enviar_api.post(request=fake_request).data

        elif proyecto.tipo_envio == "manual" and creados:
            for creado in creados:
                DetalleEnvio.objects.filter(medio_id=creado["id"]).update(
                    fecha_programada=timezone.now() + timedelta(hours=12)
                )
            envio_resultado = {
                "estado": "manual_programado",
                "detalle": f"Se programaron {len(creados)} artículos para envío"
            }

        return Response(
            {
                "mensaje": f"{len(creados)} artículos creados.",
                "creados": creados,
                "errores": errores,
                "envio": envio_resultado if envio_resultado else "no_aplica",
            },
            status=201 if creados else 400,
        )
