from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.base.models import Articulo,Redes,DetalleEnvio
from apps.proyectos.models import Proyecto
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.utils import timezone



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
            return Response(
                {"error": "Se requieren 'proyecto_id' y 'articulos'"},
                status=400
            )

        proyecto = Proyecto.objects.filter(id=proyecto_id).first()
        if not proyecto:
            return Response({"error": "Proyecto no encontrado"}, status=404)

        # 🔹 Recuperamos el system_user
        User = get_user_model()
        system_user = User.objects.filter(id=2).first()
        if system_user:
            # Forzamos un correo válido
            if not system_user.email or "@" not in system_user.email:
                system_user.email = "admin@buho.media"
                system_user.save(update_fields=["email"])
        else:
            return Response({"error": "Usuario del sistema no encontrado"}, status=500)

        creados, errores = [], []

        for data in articulos_data:
            titulo = data.get("titulo")
            contenido = data.get("contenido")
            url = data.get("url")
            fecha = data.get("fecha_publicacion")
            medio = data.get("medio")
            autor = data.get("autor")

            if not url or not url.strip():
                errores.append({
                    "titulo": titulo,
                    "error": "La URL es obligatoria"
                })
                continue

            if Articulo.objects.filter(url=url.strip(), proyecto=proyecto).exists():
                errores.append({
                    "url": url,
                    "error": "La URL ya existe en este proyecto"
                })
                continue

            # 🔹 Normalizamos fecha
            fecha_final = None
            if fecha:
                try:
                    # lo parseas si viene como string con datetime.fromisoformat(fecha)
                    # aquí supongo que ya es datetime
                    fecha_final = timezone.make_aware(fecha) if timezone.is_naive(fecha) else fecha
                except Exception:
                    fecha_final = timezone.now()
            else:
                fecha_final = timezone.now()

            articulo = Articulo.objects.create(
                titulo=titulo,
                contenido=contenido,
                url=url.strip(),
                fecha_publicacion=fecha_final,
                medio=medio,
                autor=autor,
                proyecto=proyecto,
                create_by=system_user  # 🔹 se asigna el usuario del sistema
            )

            # 🔹 Creamos detalle de envío automático
            DetalleEnvio.objects.create(
                estado_enviado=False,
                estado_revisado=False,
                articulo=articulo,
                proyecto_id=proyecto.id,
                fecha_programada=timezone.now() + timedelta(hours=12),
                create_by=system_user
            )

            creados.append({
                "id": articulo.id,
                "url": articulo.url,
                "fecha": articulo.fecha_publicacion
            })

        return Response(
            {
                "mensaje": f"{len(creados)} artículos creados.",
                "creados": creados,
                "errores": errores
            },
            status=201 if creados else 400
        )