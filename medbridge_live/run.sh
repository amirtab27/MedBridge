#!/usr/bin/env bash
# ./run.sh            -> http://localhost:8000   (one laptop, two Chrome windows)
# ./run.sh --https    -> https://<LAN-IP>:8000   (second device on same Wi-Fi; mics need https off-localhost)
cd "$(dirname "$0")"
PY=.venv/bin/python; [ -x $PY ] || PY=python3
if [ "$1" = "--https" ]; then
  [ -f .cert/key.pem ] || { mkdir -p .cert && openssl req -x509 -newkey rsa:2048 -nodes -days 7 -subj "/CN=medbridge" \
      -keyout .cert/key.pem -out .cert/cert.pem 2>/dev/null; }
  IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I | awk '{print $1}')
  echo "Doctor:  https://$IP:8000/?r=doctor&s=demo"
  echo "Patient: https://$IP:8000/?r=patient&l=hi&s=demo   (accept the self-signed cert warning)"
  exec $PY -m uvicorn medbridge.server:app --host 0.0.0.0 --port 8000 --ssl-keyfile .cert/key.pem --ssl-certfile .cert/cert.pem
fi
exec $PY -m uvicorn medbridge.server:app --host 0.0.0.0 --port 8000
