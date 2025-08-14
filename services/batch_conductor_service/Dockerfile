FROM python:3.11-slim

# ------------------------------------------------------------------
# Environment
# ------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    LOG_LEVEL=INFO \
    PORT=4002 \
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    PDM_USE_VENV=false

# ------------------------------------------------------------------
# Base layer & deps
# ------------------------------------------------------------------
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir pdm

# Shared python packages first (leverages Docker cache)
COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/

# Copy service code
COPY services/batch_conductor_service/ /app/services/batch_conductor_service/

# Install deps declared in this service's pyproject
WORKDIR /app/services/batch_conductor_service
# Use --frozen-lockfile to skip lockfile generation and avoid segmentation faults
COPY pdm.lock /app/services/batch_conductor_service/pdm.lock
RUN pdm install --prod --frozen-lockfile

# ------------------------------------------------------------------
# Non-root execution
# ------------------------------------------------------------------
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser
USER appuser

EXPOSE ${PORT}

CMD ["pdm", "run", "start"]
