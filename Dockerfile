FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8090 \
    TRANSCRIPT_DATA_DIR=/data \
    TRANSCRIPT_STATIC_DIR=/app/static \
    PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir openai-whisper

COPY app.py ./
COPY static ./static

RUN mkdir -p /data && python -m py_compile app.py

EXPOSE 8090
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

CMD ["python", "app.py"]
