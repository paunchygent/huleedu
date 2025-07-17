FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    API_GATEWAY_SERVICE_LOG_LEVEL=INFO \
    API_GATEWAY_SERVICE_PORT=8080 \
    API_GATEWAY_SERVICE_HOST=0.0.0.0 \
    PDM_USE_VENV=false

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir pdm

# Copy shared local dependencies first
COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/

# Now, handle the specific service
COPY services/api_gateway_service/ /app/services/api_gateway_service/

# Set working directory to the service
WORKDIR /app/services/api_gateway_service

# Install dependencies for the api_gateway_service using its own pyproject.toml
RUN pdm install --prod

# Setup user and permissions. Note: chown needs to be run as root.
USER root
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE ${API_GATEWAY_SERVICE_PORT}

# Command to run the application from the service directory
CMD ["pdm", "run", "start"] 