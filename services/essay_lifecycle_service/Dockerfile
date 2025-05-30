FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    LOG_LEVEL=INFO \
    HTTP_PORT=6000 \
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    CONTENT_SERVICE_URL=http://content_service:8000/v1/content \
    PDM_USE_VENV=false

# Set base WORKDIR for the application
WORKDIR /app

# Install PDM globally in the image
RUN pip install --no-cache-dir pdm

# Copy shared local dependencies first
COPY common_core/ /app/common_core/
COPY services/libs/ /app/services/libs/

# Now, handle the specific service
COPY services/essay_lifecycle_service/ /app/services/essay_lifecycle_service/

# Switch to service directory for dependency installation
WORKDIR /app/services/essay_lifecycle_service

# Install dependencies for the essay_lifecycle_service using its own pyproject.toml
# PDM will use the overrides to find local dependencies at the correct paths
RUN pdm install --prod

# Create data directory for essay lifecycle state storage
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    mkdir -p /data/essay_lifecycle && \
    chown -R appuser:appuser /data/essay_lifecycle && \
    chown -R appuser:appuser /app
USER appuser

# Expose the port the app runs on
EXPOSE ${HTTP_PORT}

# Command to run the HTTP application from service directory
# Note: Worker mode (worker_main.py) can be started separately if needed
CMD ["pdm", "run", "start"] 