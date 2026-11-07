FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000 \
    TRANSCRIPT_DATA_DIR=/tmp/transcript-data \
    TRANSCRIPT_STATIC_DIR=/app/free_public/static \
    PYTHONPATH=/app

WORKDIR /app

# ffmpeg captures frames. nodejs is yt-dlp's YouTube JS runtime.
# A local speech model is intentionally not installed: it does not fit a 512MB free instance.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY src/free_public /app/free_public

RUN mkdir -p /tmp/transcript-data \
    && python -m py_compile free_public/app.py free_public/captions.py free_public/screenshots.py

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

CMD ["python", "-m", "free_public.app"]
