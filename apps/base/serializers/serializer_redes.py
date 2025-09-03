from rest_framework import serializers
from apps.base.models import Redes

class RedesSerializer(serializers.ModelSerializer):
    proyecto_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Redes
        fields = '__all__'  
    
    def get_proyecto_nombre(self, obj):
        return obj.proyecto.nombre if obj.proyecto else None