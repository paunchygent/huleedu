# Multi-stage build for optimized production image
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PDM_USE_VENV=false

# Install build dependencies (for compilation)
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
COPY services/identity_service/ /app/services/identity_service/

# Switch to service directory and install dependencies
WORKDIR /app/services/identity_service
COPY pdm.lock /app/services/identity_service/pdm.lock
RUN pdm install --prod --frozen-lockfile

# Final runtime stage
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    IDENTITY_SERVICE_LOG_LEVEL=INFO \
    IDENTITY_SERVICE_HTTP_PORT=7005 \
    IDENTITY_SERVICE_PROMETHEUS_PORT=9097 \
    IDENTITY_SERVICE_HOST=0.0.0.0 \
    PDM_USE_VENV=false

# Install ONLY runtime dependencies (no build tools)
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
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser \
    && chown -R appuser:appuser /app

USER appuser
WORKDIR /app/services/identity_service

EXPOSE ${IDENTITY_SERVICE_HTTP_PORT}
EXPOSE ${IDENTITY_SERVICE_PROMETHEUS_PORT}

# Command to run the application
CMD ["pdm", "run", "start"]