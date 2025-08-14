# Multi-stage build for optimized production image
FROM python:3.11-slim as builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PDM_USE_VENV=false

# Install build dependencies (for consistency and future-proofing)
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install PDM
RUN pip install --no-cache-dir pdm

# Set working directory
WORKDIR /app

# Copy shared local dependencies
COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/

# Copy service files
COPY services/essay_lifecycle_service/ /app/services/essay_lifecycle_service/

# Switch to service directory and install dependencies
WORKDIR /app/services/essay_lifecycle_service
RUN pdm install --prod --frozen-lockfile

# Final runtime stage
FROM python:3.11-slim as runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    LOG_LEVEL=INFO \
    HTTP_PORT=6000 \
    PROMETHEUS_PORT=9090 \
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    CONTENT_SERVICE_URL=http://content_service:8000/v1/content \
    PDM_USE_VENV=false

# Install only runtime dependencies (no build tools)
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install PDM in runtime (needed for pdm run command)
RUN pip install --no-cache-dir pdm

# Create application directory
WORKDIR /app

# Copy the built application and dependencies from builder stage
COPY --from=builder /app /app

# Create user, data directory, and set permissions
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser \
    && mkdir -p /data/essay_lifecycle \
    && chown -R appuser:appuser /data/essay_lifecycle \
    && chown -R appuser:appuser /app

USER appuser
WORKDIR /app/services/essay_lifecycle_service

# Expose the ports the app runs on
EXPOSE ${HTTP_PORT} ${PROMETHEUS_PORT}

# Command to run the HTTP application from service directory
# Note: Worker mode (worker_main.py) can be started separately if needed
CMD ["pdm", "run", "start"]