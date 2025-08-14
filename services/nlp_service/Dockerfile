# Multi-stage build for smaller final image
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PDM_USE_VENV=false

# Install build dependencies
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
COPY services/nlp_service/ /app/services/nlp_service/

# Switch to service directory and install dependencies
WORKDIR /app/services/nlp_service
COPY pdm.lock /app/services/nlp_service/pdm.lock
RUN pdm install --prod --frozen-lockfile

# Final runtime stage
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    LOG_LEVEL=INFO \
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    CONTENT_SERVICE_URL=http://content_service:8000/v1/content \
    SERVICE_NAME=nlp_service \
    PDM_USE_VENV=false

# Install only runtime dependencies
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

# Create user and set permissions
RUN groupadd -r nlpuser && useradd --no-log-init -r -g nlpuser nlpuser \
    && chown -R nlpuser:nlpuser /app

USER nlpuser
WORKDIR /app/services/nlp_service

# Command to run the worker service
CMD ["pdm", "run", "start"]