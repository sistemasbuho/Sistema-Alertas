from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics

from rest_framework import status
from apps.base.models import TemplateConfig
from apps.base.serializers.serializer_templates_mensaje import CampoPlantillaSerializer,PlantillaSerializer


class CrearPlantillaAPIView(APIView):
    def post(self, request):
        serializer = PlantillaSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ListarPlantillasAPIView(generics.ListAPIView):
    serializer_class = PlantillaSerializer

    def get_queryset(self):
        """
        Filtra las plantillas solo por el proyecto recibido en query params.
        Ejemplo: /api/plantillas/?proyecto_id=xxxx
        """
        proyecto_id = self.request.query_params.get("proyecto_id")
        if not proyecto_id:
            return TemplateConfig.objects.none()  # evita devolver todas
        return TemplateConfig.objects.filter(proyecto_id=proyecto_id)


class CrearCamposPlantillaAPIView(APIView):
    def post(self, request, plantilla_id):
        """
        Crea múltiples campos asociados a una plantilla ya existente.
        """
        try:
            plantilla = TemplateConfig.objects.get(id=plantilla_id)
        except TemplateConfig.DoesNotExist:
            return Response({"error": "Plantilla no encontrada"}, status=status.HTTP_404_NOT_FOUND)

        # Pasamos la relación explícita en cada campo
        campos_data = request.data.get("campos", [])
        for campo in campos_data:
            campo["plantilla"] = plantilla.id

        serializer = CampoPlantillaSerializer(data=campos_data, many=True)
        if serializer.is_valid():
            serializer.save(plantilla=plantilla)  # asociamos todos los campos a la plantilla
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)