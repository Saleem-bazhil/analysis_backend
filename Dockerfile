# =========================
# 1. Builder Stage
# =========================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip wheel

COPY requirements.txt .

RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt


# =========================
# 2. Runtime Stage
# =========================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/app \
    PORT=9000

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq5 \
    netcat-openbsd \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system app && adduser --system --group app --home /home/app

RUN mkdir -p /home/app && chown -R app:app /home/app

COPY --from=builder /wheels /wheels
COPY requirements.txt .

RUN pip install --no-cache-dir /wheels/*

COPY . .

RUN chown -R app:app /app

# Collect static files
RUN python manage.py collectstatic --noinput

USER app

# Compile python files
RUN python -m compileall .

# Expose new port
EXPOSE 9000

# Healthcheck updated port
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl --fail http://localhost:9000/ || exit 1

# Run Gunicorn on dynamic PORT
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --threads 2 --max-requests 1000 --max-requests-jitter 100 --timeout 60"]