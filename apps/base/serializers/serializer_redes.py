from rest_framework import serializers
from apps.base.models import Redes

class RedesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Redes
        fields = '__all__'  