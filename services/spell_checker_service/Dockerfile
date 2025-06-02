FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    LOG_LEVEL=INFO \
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
COPY services/spell_checker_service/ /app/services/spell_checker_service/

# Switch to service directory for dependency installation
WORKDIR /app/services/spell_checker_service

# Install dependencies for the spell_checker_service using its own pyproject.toml
# PDM will use the overrides to find local dependencies at the correct paths
RUN pdm install --prod

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser
USER appuser

# Command to run the application from service directory
CMD ["pdm", "run", "start_worker"] 