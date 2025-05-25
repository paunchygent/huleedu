FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENV_TYPE=docker \
    LOG_LEVEL=INFO \
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    CONTENT_SERVICE_URL=http://content_service:8000/v1/content

WORKDIR /app

RUN pip install --no-cache-dir pdm

# Copy common_core and libs from repo root context
COPY common_core ./common_core/
COPY services/libs ./libs/
COPY services/spell_checker_service/pyproject.toml services/spell_checker_service/pdm.lock ./

# Install dependencies. PDM will use the local common_core due to path dependency.
RUN pdm install --prod --no-lock # --no-lock to ensure it respects the path dep

COPY services/spell_checker_service/worker.py ./

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser
USER appuser

CMD ["pdm", "run", "start_worker"] 