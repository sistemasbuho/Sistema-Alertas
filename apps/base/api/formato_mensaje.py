from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics

from rest_framework import status
from apps.base.models import TemplateConfig,TemplateCampoConfig
from apps.base.serializers.serializer_templates_mensaje import CampoPlantillaSerializer,PlantillaSerializer
from django.shortcuts import get_object_or_404


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
    def put(self, request, plantilla_id):
        """
        Crea o actualiza la configuración de los campos de una plantilla.
        - Si un campo ya existe en `config_campos`, se actualiza (orden/estilo).
        - Si no existe, se agrega.
        """
        plantilla = get_object_or_404(TemplateConfig, id=plantilla_id)
        campos_data = request.data.get("campos", [])

        # Cargamos lo que ya tenga guardado
        config_actual = plantilla.config_campos or {}

        for campo in campos_data:
            nombre_campo = campo.get("campo")
            if not nombre_campo:
                return Response(
                    {"error": "Cada campo debe incluir 'campo'"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            config_existente = config_actual.get(nombre_campo, {})
            nueva_config = config_existente.copy()

            for clave, valor in campo.items():
                if clave == "campo":
                    continue
                nueva_config[clave] = valor

            config_actual[nombre_campo] = nueva_config

        # Guardamos en la plantilla
        plantilla.config_campos = config_actual
        plantilla.save()

        return Response(config_actual, status=status.HTTP_200_OK)
