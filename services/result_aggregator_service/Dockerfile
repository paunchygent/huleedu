FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    LOG_LEVEL=INFO \
    PORT=4003 \
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
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
COPY services/result_aggregator_service/ /app/services/result_aggregator_service/

# Set working directory to the service
WORKDIR /app/services/result_aggregator_service

# Install dependencies for the result_aggregator_service using its own pyproject.toml
RUN pdm install --prod

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser
USER appuser

EXPOSE ${PORT}

# Command to run the application from service directory
CMD ["pdm", "run", "start"]