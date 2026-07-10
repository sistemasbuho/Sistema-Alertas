from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ia.models import MatrizCliente
from apps.ia.serializers.serializer_matriz import MatrizClienteSerializer
from apps.proyectos.models import Proyecto


class MatrizClienteAPIView(APIView):
    """GET/PUT /api/ia/matriz/<proyecto_id>/ — matriz digitalizada del cliente.

    GET devuelve una matriz default-inicializada (no persistida) si el
    proyecto aún no tiene, para que el frontend edite sin baile de 404.
    """

    def get(self, request, proyecto_id):
        proyecto = get_object_or_404(Proyecto, id=proyecto_id)
        matriz = MatrizCliente.objects.filter(proyecto=proyecto).first()
        if matriz is None:
            matriz = MatrizCliente(proyecto=proyecto)
        data = MatrizClienteSerializer(matriz).data
        data["proyecto"] = str(proyecto.id)
        return Response(data)

    def put(self, request, proyecto_id):
        proyecto = get_object_or_404(Proyecto, id=proyecto_id)
        matriz = MatrizCliente.objects.filter(proyecto=proyecto).first()

        serializer = MatrizClienteSerializer(
            matriz, data=request.data, partial=matriz is not None
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(proyecto=proyecto)
        return Response(
            serializer.data,
            status=status.HTTP_200_OK if matriz else status.HTTP_201_CREATED,
        )
