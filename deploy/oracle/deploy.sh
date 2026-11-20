#!/usr/bin/env bash
# Sube ATLAS al servidor de Oracle Cloud y lo (re)levanta con Docker.
#
#   bash deploy/oracle/deploy.sh <IP>                  # subir/actualizar el código
#   bash deploy/oracle/deploy.sh <IP> --migrate-data   # además copiar la base de la PC (memoria, recordatorios)
#   bash deploy/oracle/deploy.sh <IP> --publish        # además encender el túnel: atlas.sirinetrd.com pasa al servidor
#                                                      # (antes, apagar el túnel de la PC)
#
# Antes, una sola vez: python deploy/oracle/prepare_secrets.py
# Requiere la llave ~/.ssh/atlas_oracle (la pública se cargó al crear la máquina).
set -euo pipefail

IP="${1:?Uso: deploy.sh <IP> [--migrate-data] [--publish]}"
shift
MIGRATE=""; PUBLISH=""
for flag in "$@"; do
  case "$flag" in
    --migrate-data) MIGRATE="--migrate-data" ;;
    --publish) PUBLISH="--publish" ;;
    *) echo "Opción desconocida: $flag"; exit 1 ;;
  esac
done
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/deploy/oracle"
KEY="${ATLAS_SSH_KEY:-$HOME/.ssh/atlas_oracle}"
REMOTE="ubuntu@$IP"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 "$REMOTE")
SCP=(scp -i "$KEY" -o StrictHostKeyChecking=accept-new)

[ -f "$HERE/secrets/server.env" ] || { echo "Falta secrets/server.env: corre primero prepare_secrets.py"; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
echo "== Empaquetando el backend"
tar -C "$ROOT" -czf "$STAGE/atlas.tgz" \
  --exclude='__pycache__' --exclude='*.pyc' \
  backend/app backend/Dockerfile backend/.dockerignore backend/requirements-server.txt
cp "$HERE/docker-compose.yml" "$STAGE/"
tar -C "$HERE/secrets" -czf "$STAGE/secrets.tgz" server.env cloudflared

if [ "$MIGRATE" = "--migrate-data" ]; then
  echo "== Incluyendo los datos de la PC (memoria, recordatorios, personalidad)"
  mkdir -p "$STAGE/data/models/speaker"
  cp "$ROOT/backend/atlas.db" "$STAGE/data/"
  [ -f "$ROOT/backend/speaker_profile.json" ] && cp "$ROOT/backend/speaker_profile.json" "$STAGE/data/"
  [ -f "$ROOT/.cache/speaker/voxceleb_resnet34_LM.onnx" ] && cp "$ROOT/.cache/speaker/voxceleb_resnet34_LM.onnx" "$STAGE/data/models/speaker/"
  tar -C "$STAGE" -czf "$STAGE/data.tgz" data
fi

echo "== Subiendo a $IP"
"${SCP[@]}" "$STAGE"/*.tgz "$STAGE/docker-compose.yml" "$REMOTE:/tmp/"

echo "== Instalando y levantando en el servidor"
"${SSH[@]}" "MIGRATE='$MIGRATE' PUBLISH='$PUBLISH' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail
if ! command -v docker >/dev/null; then
  echo "-- Instalando Docker"
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker.io docker-compose-v2
  sudo systemctl enable --now docker
fi
sudo mkdir -p /opt/atlas/data /opt/atlas/cloudflared
sudo rm -rf /opt/atlas/backend
sudo tar -C /opt/atlas -xzf /tmp/atlas.tgz
sudo cp /tmp/docker-compose.yml /opt/atlas/
# Lo secreto se instala solo la primera vez: después, server.env guarda también
# lo que se cambie desde la app (por ejemplo, la voz elegida).
TMP=$(mktemp -d)
tar -C "$TMP" -xzf /tmp/secrets.tgz
[ -f /opt/atlas/data/server.env ] || sudo cp "$TMP/server.env" /opt/atlas/data/server.env
sudo cp "$TMP"/cloudflared/* /opt/atlas/cloudflared/
sudo chmod 644 /opt/atlas/cloudflared/*   # cloudflared corre como usuario sin privilegios
if [ "$MIGRATE" = "--migrate-data" ]; then
  sudo docker compose -f /opt/atlas/docker-compose.yml stop atlas 2>/dev/null || true
  sudo tar -C /opt/atlas -xzf /tmp/data.tgz
fi
sudo chmod 600 /opt/atlas/data/server.env
rm -rf "$TMP" /tmp/atlas.tgz /tmp/secrets.tgz /tmp/data.tgz /tmp/docker-compose.yml
cd /opt/atlas
if [ "$PUBLISH" = "--publish" ]; then
  sudo docker compose --profile public up -d --build
else
  sudo docker compose up -d --build atlas
fi
sudo docker compose --profile public ps
REMOTE_SCRIPT

echo "== Listo. Revisa: curl https://atlas.sirinetrd.com/api/v1/system/health"
