from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from social_django.utils import load_strategy, load_backend
from django.contrib.auth import login
from rest_framework_simplejwt.tokens import RefreshToken

class GoogleLoginAPIView(APIView):
    permission_classes = [AllowAny] 

    def post(self, request):
        token = (
            request.data.get("id_token")
            or request.data.get("access_token")
            or request.data.get("token")
        )
        if not token:
            return Response({"error": "No token provided"}, status=status.HTTP_400_BAD_REQUEST)

        strategy = load_strategy(request)
        backend = load_backend(strategy=strategy, name='google-oauth2', redirect_uri=None)

        try:
            user = backend.do_auth(token)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if user and user.is_active:
            login(request, user)

            # Emitimos JWT propio (SimpleJWT)
            refresh = RefreshToken.for_user(user)
            return Response({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "username": user.get_username(),
                    "email": getattr(user, "email", None),
                }
            }, status=status.HTTP_200_OK)

        return Response({"error": "Authentication failed"}, status=status.HTTP_400_BAD_REQUEST)
