FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    CLASS_MANAGEMENT_SERVICE_LOG_LEVEL=INFO \
    CLASS_MANAGEMENT_SERVICE_PORT=5002 \
    CLASS_MANAGEMENT_SERVICE_HOST=0.0.0.0 \
    PDM_USE_VENV=false

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir pdm

# Copy shared local dependencies first
COPY common_core/ /app/common_core/
COPY services/libs/ /app/services/libs/

# Now, handle the specific service
COPY services/class_management_service/ /app/services/class_management_service/

# Set working directory to the service
WORKDIR /app/services/class_management_service

# Install dependencies for the class_management_service using its own pyproject.toml
RUN pdm install --prod

# Setup user and permissions. Note: chown needs to be run as root.
USER root
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE ${CLASS_MANAGEMENT_SERVICE_PORT}

# Command to run the application from the service directory
CMD ["pdm", "run", "start"]

