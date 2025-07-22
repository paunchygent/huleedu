FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    LOG_LEVEL=INFO \
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    CONTENT_SERVICE_URL=http://content_service:8000/v1/content \
    PDM_USE_VENV=false

# Set base WORKDIR for the application
WORKDIR /app

# Install system dependencies for health checks and PDM
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pdm

# Copy shared local dependencies first
COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/

# Now, handle the specific service
COPY services/spellchecker_service/ /app/services/spellchecker_service/

# Switch to service directory for dependency installation
WORKDIR /app/services/spellchecker_service

# Install dependencies for the spellchecker_service using its own pyproject.toml
# PDM will use the overrides to find local dependencies at the correct paths
# Use --frozen-lockfile to skip lockfile generation and avoid segmentation faults
RUN pdm install --prod --frozen-lockfile

# Ensure runtime user can write logs/corrections
RUN mkdir -p /app/services/spellchecker_service/data/corrected_essays \
    && chown -R 1000:1000 /app/services/spellchecker_service/data \
    && groupadd -r appuser && useradd --no-log-init -r -g appuser -u 1000 appuser
USER appuser

# Health check for combined service (HTTP API + Kafka worker)
HEALTHCHECK --interval=15s --timeout=5s --retries=3 --start-period=20s \
    CMD curl -f http://localhost:8002/healthz || exit 1

# Command to run the integrated service (HTTP API + Kafka worker)
CMD ["pdm", "run", "start"] 