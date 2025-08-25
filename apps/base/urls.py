from django.urls import path
from apps.base.api.login import GoogleLoginAPIView

urlpatterns = [
    path("auth/google/", GoogleLoginAPIView.as_view(), name="google-login"),
]
