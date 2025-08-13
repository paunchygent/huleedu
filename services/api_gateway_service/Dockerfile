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
COPY services/api_gateway_service/ /app/services/api_gateway_service/

# Switch to service directory and install dependencies
WORKDIR /app/services/api_gateway_service
RUN pdm install --prod --frozen-lockfile

# Final runtime stage
FROM python:3.11-slim as runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    API_GATEWAY_SERVICE_LOG_LEVEL=INFO \
    API_GATEWAY_SERVICE_PORT=8080 \
    API_GATEWAY_SERVICE_HOST=0.0.0.0 \
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

# Create user and set permissions
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser \
    && chown -R appuser:appuser /app

USER appuser
WORKDIR /app/services/api_gateway_service

EXPOSE ${API_GATEWAY_SERVICE_PORT}

# Command to run the application
CMD ["pdm", "run", "start"]