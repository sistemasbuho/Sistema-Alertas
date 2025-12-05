from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from script.brightdata import buscar_interacciones


class BrightDataSnapshotAPIView(APIView):
    """Crea snapshots en Bright Data a partir de una o varias URLs."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        urls = request.data.get("urls") or request.data.get("url")
        red_social = request.data.get("red_social")

        if not red_social:
            return Response(
                {"error": "Se requiere 'red_social' para seleccionar el dataset."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not urls:
            return Response(
                {"error": "Se requiere al menos una URL en 'urls' o 'url'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if isinstance(urls, str):
            urls = [urls]

        if not isinstance(urls, (list, tuple)):
            return Response(
                {"error": "El campo 'urls' debe ser una lista de cadenas."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        snapshots = []
        errores = []

        for url in urls:
            if not url:
                errores.append({"url": url, "error": "URL vacía."})
                continue

            try:
                snapshot_id = buscar_interacciones(url, red_social)
            except ValueError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as exc:  # pragma: no cover - errores inesperados
                errores.append({"url": url, "error": f"Error al solicitar snapshot: {exc}"})
                continue

            if snapshot_id:
                snapshots.append({"url": url, "snapshot_id": snapshot_id})
            else:
                errores.append({"url": url, "error": "No se obtuvo snapshot_id"})

        estado = status.HTTP_200_OK if snapshots else status.HTTP_502_BAD_GATEWAY
        return Response({"snapshots": snapshots, "errores": errores}, status=estado)
