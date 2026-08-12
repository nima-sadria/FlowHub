# -- Stage 1: Build React frontend ---------------------------------------------
FROM node:20-alpine AS frontend-build

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci --silent
# Channel Docs imports these repository contracts as raw Vite modules.  The
# frontend build runs from /frontend, so include the explicit parent path the
# source imports resolve to instead of relying on a host checkout layout.
COPY docs/api/channel/*.md /docs/api/channel/
COPY frontend/ ./
ARG VITE_HANDSONTABLE_LICENSE_KEY
RUN npm run build

# -- Stage 2: Python application -----------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# curl: required for compose healthcheck and diagnostic verification
# tzdata: required by zoneinfo for IANA timezone validation on slim images
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# app.flowhub.app resolves: Path(__file__).parent.parent.parent / "frontend" / "dist"
# From /app/app/flowhub/app.py that path is /app/frontend/dist
COPY --from=frontend-build /frontend/dist ./frontend/dist

RUN mkdir -p /data/storage /data/backups /data/logs

EXPOSE 8085

CMD ["uvicorn", "app.flowhub.app:app", "--host", "0.0.0.0", "--port", "8085", \
     "--log-level", "info", "--access-log"]
