# Backend de ATLAS para un servidor Linux (probado para Oracle Cloud Ampere, ARM64;
# también sirve en x86_64). Se levanta con deploy/oracle/docker-compose.yml.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/data/hf \
    ATLAS_ENV_FILE=/data/server.env

# espeak-ng: fonética en español para Kokoro. libsndfile/ffmpeg: audio de voz.
RUN apt-get update \
    && apt-get install -y --no-install-recommends espeak-ng libsndfile1 ffmpeg tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# PyTorch solo-CPU (el servidor no tiene GPU): mucho más liviano que el de PyPI.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements-server.txt .
RUN pip install -r requirements-server.txt

COPY app ./app

EXPOSE 8000
# proxy-headers: la IP real del visitante llega desde Cloudflare (solo cloudflared
# alcanza este puerto: no se publica fuera de la red de Docker).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
