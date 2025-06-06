FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    FILE_SERVICE_LOG_LEVEL=INFO \
    FILE_SERVICE_HTTP_PORT=7001 \
    FILE_SERVICE_PROMETHEUS_PORT=9092 \
    FILE_SERVICE_HOST=0.0.0.0 \
    PDM_USE_VENV=false

# Set base WORKDIR for the application
WORKDIR /app

# Install curl for health checks and PDM globally in the image
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir pdm

# Copy shared local dependencies first
COPY common_core/ /app/common_core/
COPY services/libs/ /app/services/libs/

# Now, handle the specific service
COPY services/file_service/ /app/services/file_service/

# Switch to service directory for dependency installation
WORKDIR /app/services/file_service

# Install dependencies for the file_service using its own pyproject.toml
# PDM will use the overrides to find local dependencies at the correct paths
RUN pdm install --prod

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose the ports the app runs on
EXPOSE ${FILE_SERVICE_HTTP_PORT}
EXPOSE ${FILE_SERVICE_PROMETHEUS_PORT}

# Command to run the application from service directory
CMD ["pdm", "run", "start"] 