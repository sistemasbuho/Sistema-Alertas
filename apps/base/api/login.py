from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
# from social_django.utils import load_strategy, load_backend
from django.contrib.auth import login
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import serializers
from rest_framework import viewsets, permissions, status, filters

import google.auth.transport.requests
import google.oauth2.id_token
from django.contrib.auth.models import User

# User = get_user_model()

## SERIALIZERS
class UserParcialSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "is_superuser", "is_staff"]

class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    jwt_google = serializers.CharField(required=True)

    def create(self, validated_data):
        return validated_data

def loginTokenUser(request, user):
    
    if not user.is_active:
        return Response({"detail": "Usuario inactivo"},status=status.HTTP_401_UNAUTHORIZED)
    login(request, user)

    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    refresh_token = str(refresh)
    
    tokens = {"access":access_token, "refresh":refresh_token}
    # Obtener el nombre del grupo
    tokens.update(UserParcialSerializer(user).data)
    return tokens


class UserValidationGoogle(APIView):
    permission_classes = [permissions.AllowAny,]

    def validate_google_token(self, token):
        """
        Validar el token JWT de Google asegurando que el token sea para el cliente específico.
        """
        try:
            # Configura el transport request para validar el token
            request = google.auth.transport.requests.Request()

            # Verifica el token con el client_id
            id_info = google.oauth2.id_token.verify_oauth2_token(token, request)

            # Verifica si el token es válido y está emitido para la audiencia esperada
            if 'accounts.google.com' not in id_info['iss']:
                raise ValueError('El emisor del token no es válido.')

            return id_info
        except ValueError as e:
            # Si el token es inválido o no puede ser validado
            print(f"Error al validar el token: {e}")
            return None

    def post(self, request):
        """
        JWT para usuarios de 'Google'

        Retornar credenciales si el usuario que inició sesión con Google está autorizado por un admin a entrar a la plataforma.
        """
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        jwt_google = serializer.validated_data['jwt_google']

        # Validar el token de Google
        id_info = self.validate_google_token(jwt_google)

        if id_info is None:
            return Response({"message": "Token JWT de Google inválido."}, status=status.HTTP_401_UNAUTHORIZED)

        # Verificar que el email extraído del token coincide con el email enviado
        if id_info['email'] != email:
            return Response({"message": "El email del token no coincide."}, status=status.HTTP_401_UNAUTHORIZED)

        # Comprobar si el usuario está registrado en la base de datos
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'El correo proporcionado no se encuentra registrado'}, status=status.HTTP_404_NOT_FOUND)

        # Generar los tokens o credenciales necesarias
        tokens = loginTokenUser(request, user)

        return Response(tokens, status=status.HTTP_200_OK)