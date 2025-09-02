from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.contrib.auth import get_user_model, login
from rest_framework_simplejwt.tokens import RefreshToken
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from django.conf import settings

User = get_user_model()

class GoogleLoginAPIView(APIView):
    permission_classes = [AllowAny] 

    def post(self, request):
        token = request.data.get("credential")  # viene del frontend
        if not token:
            return Response({"error": "No token provided"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Validar el token contra el CLIENT_ID configurado en settings
            client_id = getattr(settings, "SOCIAL_AUTH_GOOGLE_OAUTH2_KEY", None)
            if not client_id:
                return Response({"error": "Google CLIENT_ID not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            idinfo = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                audience=client_id
            )

            email = idinfo.get("email")
            name = idinfo.get("name", "")
            picture = idinfo.get("picture", "")

            if not email:
                return Response({"error": "No email found in token"}, status=status.HTTP_400_BAD_REQUEST)

            user, created = User.objects.get_or_create(
                email=email,
                defaults={"username": email.split("@")[0]}
            )
            
            if created:
                user.first_name = name
                user.save()

            # Iniciar sesión en Django
            login(request, user)

            # Emitir JWT
            refresh = RefreshToken.for_user(user)
            return Response({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "name": name,
                    "picture": picture,
                }
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({"error": f"Invalid token: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Evita 500 genérico, devuelve error controlado
            return Response({"error": f"Unexpected error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
