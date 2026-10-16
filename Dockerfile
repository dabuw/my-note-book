FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5001

WORKDIR /app

# Install dependencies first so the layer is cached across code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Secrets are NEVER baked into the image. .env is excluded via .dockerignore
# and injected at runtime by docker compose (env_file).
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/database \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5001

# Uses the stdlib only, so no extra packages are needed in the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5001/api/health', timeout=4).status == 200 else 1)"

CMD ["gunicorn", "--config", "gunicorn.conf.py", "src.main:app"]
