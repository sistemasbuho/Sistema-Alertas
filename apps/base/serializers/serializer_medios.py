from rest_framework import serializers
from apps.base.models import Articulo

class MediosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Articulo
        fields = '__all__'
