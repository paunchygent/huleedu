FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    LLM_PROVIDER_SERVICE_LOG_LEVEL=INFO \
    LLM_PROVIDER_SERVICE_PORT=8080 \
    LLM_PROVIDER_SERVICE_HOST=0.0.0.0 \
    PDM_USE_VENV=false

# Set base WORKDIR for the application
WORKDIR /app

# Install curl for health checks and PDM globally in the image
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir pdm

# Copy shared local dependencies first
COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/

# Now, handle the specific service
COPY services/llm_provider_service/ /app/services/llm_provider_service/

# Switch to service directory for dependency installation
WORKDIR /app/services/llm_provider_service

# Install dependencies for the llm_provider_service using its own pyproject.toml
# PDM will use the overrides to find local dependencies at the correct paths
RUN pdm install --prod

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose the ports the app runs on
EXPOSE ${LLM_PROVIDER_SERVICE_PORT}

# Command to run the application from service directory
CMD ["pdm", "run", "start"]