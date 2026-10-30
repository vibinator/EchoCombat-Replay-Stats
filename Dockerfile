# EchoVR Replay Stats as one container (QNAP Container Station or any Docker host). See docs/Setup.MD (QNAP).

# 1) Build the website
FROM node:24-bookworm-slim AS frontend
WORKDIR /src/app/frontend
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci
COPY app/frontend/ ./
RUN npm run build

# 2) Python server + built website
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ECHOVR_DATA_DIR=/data \
    ECHOVR_REPLAY_SOURCE=/replays
WORKDIR /srv/echovr
COPY app/backend/requirements.txt app/backend/requirements.txt
RUN pip install --no-cache-dir -r app/backend/requirements.txt
COPY app/ app/
COPY --from=frontend /src/app/frontend/dist app/frontend/dist

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)"
CMD ["python", "-m", "uvicorn", "backend.main:app", "--app-dir", "app", "--host", "0.0.0.0", "--port", "8000"]
