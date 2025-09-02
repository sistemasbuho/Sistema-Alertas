from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.base.models import Articulo,Redes,DetalleEnvio
from apps.proyectos.models import Proyecto
from rest_framework.views import APIView


from django.utils.timezone import now

class ImportarArticuloAPIView(APIView):
    def post(self, request):
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

        for data in articulos_data:
            titulo = data.get("titulo")
            contenido = data.get("contenido")
            fecha = data.get("fecha")
            url = data.get("url")
            autor = data.get("autor")
            reach = data.get("reach")
            
            if not url or not url.strip():# Validar URL obligatoria
                errores.append({
                    "titulo": titulo,
                    "error": "La URL es obligatoria"
                })
                continue

            if Articulo.objects.filter(url=url, proyecto=proyecto).exists():
                errores.append({
                    "url": url,
                    "error": "La URL ya existe en este proyecto"
                })
                continue

            articulo = Articulo.objects.create(
                titulo=titulo,
                contenido=contenido,
                url=url.strip(),
                fecha_publicacion=fecha if fecha else now(),
                autor=autor,
                reach=reach,
                proyecto=proyecto
            )

            detalle_envio = DetalleEnvio.objects.create(
                estado_enviado=False,
                medio=articulo
            )
            creados.append({
                "id": articulo.id,
                "titulo": articulo.titulo,
                "url": articulo.url
            })

        return Response(
            {
                "mensaje": f"{len(creados)} artículos creados.",
                "creados": creados,
                "errores": errores
            },
            status=201 if creados else 400
        )