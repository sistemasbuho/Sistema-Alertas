# Imagen base fijada (alineada con Dockerfile.enrich); `latest` invalidaba
# toda la caché cuando el tag cambiaba en el registro.
FROM python:3.12-slim

# Evita que Python guarde archivos .pyc y usa salida sin buffer
ENV PYTHONUNBUFFERED=1

# Establece el directorio de trabajo
WORKDIR /app

# Instala dependencias del sistema necesarias
RUN apt-get update && \
    apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    ffmpeg \
    tesseract-ocr-spa && \
    rm -rf /var/lib/apt/lists/*

# Copia primero requirements.txt e instala dependencias de Python
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto de la aplicación
COPY . /app
