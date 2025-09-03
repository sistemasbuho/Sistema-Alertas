from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.timezone import now
from apps.proyectos.models import Proyecto
from apps.base.models import Redes,RedesSociales,DetalleEnvio

class ImportarRedesAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        origin = request.headers.get("X-Custom-Domain")
        if origin != "https://api.monitoreo.buho.media/":
            return Response({"error": "Dominio no autorizado"}, status=403)


        print('request.data',request.data)
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
            
            red_social_obj = None
            if red_social_nombre:
                red_social_obj = RedesSociales.objects.filter(nombre=red_social_nombre).first()


            red = Redes.objects.create(
                contenido=contenido,
                fecha=fecha if fecha else now(),
                url=url.strip(),
                autor=autor,
                reach=reach,
                engagement=engagement,
                proyecto=proyecto,
                red_social=red_social_obj 
            )

            detalle_envio = DetalleEnvio.objects.create(
                estado_enviado=False,
                red_social=red
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
