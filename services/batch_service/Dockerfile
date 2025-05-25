FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    LOG_LEVEL=INFO \
    PORT=5000 \
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    CONTENT_SERVICE_URL=http://content_service:8000/v1/content

WORKDIR /app

RUN pip install --no-cache-dir pdm

# Copy common_core and libs from repo root context
COPY common_core ./common_core/
COPY services/libs ./libs/
COPY services/batch_service/pyproject.toml services/batch_service/pdm.lock ./

RUN pdm install --prod --no-lock

COPY services/batch_service/ ./

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser
USER appuser

EXPOSE ${PORT}
CMD ["pdm", "run", "start"] 