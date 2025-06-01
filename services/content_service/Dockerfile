FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    LOG_LEVEL=INFO \
    CONTENT_STORE_ROOT_PATH=/data/huleedu_content_store \
    PORT=8000 \
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
COPY services/content_service/ /app/services/content_service/

# Switch to service directory for dependency installation
WORKDIR /app/services/content_service

# Install dependencies for the content_service using its own pyproject.toml
# PDM will use the overrides to find local dependencies at the correct paths
RUN pdm install --prod

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    mkdir -p ${CONTENT_STORE_ROOT_PATH} && \
    chown -R appuser:appuser ${CONTENT_STORE_ROOT_PATH} && \
    chown -R appuser:appuser /app
USER appuser

# Expose the port the app runs on
EXPOSE ${PORT}

# Expose the port the app runs on
EXPOSE ${PORT}

# Command to run the application from service directory
CMD ["pdm", "run", "start"] 