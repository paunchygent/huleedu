FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    LOG_LEVEL=INFO \
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    CONTENT_SERVICE_URL=http://content_service:8000/v1/content \
    SERVICE_NAME=cj_assessment_service \
    PDM_USE_VENV=false

# System dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set base WORKDIR for the application
WORKDIR /app

# Install PDM globally in the image
RUN pip install --no-cache-dir pdm

# Copy shared local dependencies first
COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/

# Now, handle the specific service
COPY services/cj_assessment_service/ /app/services/cj_assessment_service/

# Switch to service directory for dependency installation
WORKDIR /app/services/cj_assessment_service

# Install dependencies for the cj_assessment_service using its own pyproject.toml
# PDM will use the overrides to find local dependencies at the correct paths
# Use --frozen-lockfile to skip lockfile generation and avoid segmentation faults
COPY pdm.lock /app/services/cj_assessment_service/pdm.lock
RUN pdm install --prod --frozen-lockfile

RUN groupadd -r cjassessment && useradd --no-log-init -r -g cjassessment cjassessment \
    && chown -R cjassessment:cjassessment /app
USER cjassessment

# Health check (now targets /healthz endpoint)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9090/healthz || exit 1

# Command to run the integrated service (HTTP API + Kafka worker)
CMD ["pdm", "run", "start"] 