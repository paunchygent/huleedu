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

# Copy relevant parts of the monorepo for PDM to resolve local packages
COPY pyproject.toml pdm.lock /app/
COPY common_core/ /app/common_core/
COPY services/libs/ /app/services/libs/
COPY services/class_management_service/ /app/services/class_management_service/

# Install dependencies from the monorepo root
# PDM needs access to the root pyproject.toml and pdm.lock to resolve local packages
RUN pdm install --prod

# Setup user and permissions
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE ${CLASS_MANAGEMENT_SERVICE_PORT}

# Run the service from its own directory
CMD ["pdm", "run", "python", "services/class_management_service/app.py"]

