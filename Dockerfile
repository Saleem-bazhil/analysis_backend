# =========================
# 1. Builder Stage (Wheels)
# =========================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install wheel support
RUN pip install --upgrade pip wheel

# Copy only requirements (cache optimization)
COPY requirements.txt .

# Build wheels (fast install later)
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt


# =========================
# 2. Runtime Stage
# =========================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime dependencies only
RUN apt-get update && apt-get install -y \
    libpq5 \
    netcat-openbsd \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user early
RUN addgroup --system app && adduser --system --group app

# Copy wheels and install
COPY --from=builder /wheels /wheels
COPY requirements.txt .

RUN pip install --no-cache-dir /wheels/*

# Copy project
COPY . .

# Permissions
RUN chown -R app:app /app

USER app

# Compile python (faster startup)
RUN python -m compileall .

# Collect static (optional if using CDN/Nginx separately)
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Healthcheck for orchestration
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl --fail http://localhost:8000/ || exit 1

# Gunicorn optimized for production
CMD ["gunicorn", "config.wsgi:application",
     "--bind", "0.0.0.0:8000",
     "--workers", "3",
     "--threads", "2",
     "--max-requests", "1000",
     "--max-requests-jitter", "100",
     "--timeout", "60"]