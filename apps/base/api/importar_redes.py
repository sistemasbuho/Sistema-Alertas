from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.timezone import now
from apps.proyectos.models import Proyecto
from apps.base.models import Redes

class ImportarRedesAPIView(APIView):
    def post(self, request):
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

        for data in redes_data:
            contenido = data.get("contenido")
            fecha = data.get("fecha")
            url = data.get("url")
            autor = data.get("autor")
            reach = data.get("reach")
            engagement = data.get("engagement")

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

            red = Redes.objects.create(
                contenido=contenido,
                fecha=fecha if fecha else now(),
                url=url.strip(),
                autor=autor,
                reach=reach,
                engagement=engagement,
                proyecto=proyecto
            )
            creados.append({
                "id": red.id,
                "url": red.url,
                "fecha": red.fecha
            })

        return Response(
            {
                "mensaje": f"{len(creados)} publicaciones creadas.",
                "creados": creados,
                "errores": errores
            },
            status=201 if creados else 400
        )
