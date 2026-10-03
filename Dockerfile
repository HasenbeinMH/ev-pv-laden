# Dockerfile fuer das Home-Assistant-Add-on (config.yaml im selben Ordner).
# Eigenes FROM statt BUILD_FROM: der Supervisor liefert BUILD_FROM seit 2026.04 nicht mehr,
# python:3.12-slim ist Multi-Arch (amd64/aarch64) – wie beim EV Tracker.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kern-Module aus dem Hauptordner (alle, damit keins vergessen wird)
COPY *.py ./
# Web-Oberflaeche (Ingress)
COPY webapp/ ./webapp/

# Datenverzeichnis: /data stellt der Supervisor automatisch bereit (Optionen, Datenbank, Log)
ENV EVPV_DATA=/data

# Muss zum ingress_port in config.yaml passen
EXPOSE 8099
CMD ["uvicorn", "webapp.app:app", "--host", "0.0.0.0", "--port", "8099"]
