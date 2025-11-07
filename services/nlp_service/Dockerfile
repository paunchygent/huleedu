# Production-grade Dockerfile aligned with root-level PDM lockfile

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PDM_USE_VENV=false \
    PDM_IGNORE_ACTIVE_VENV=1 \
    PROJECT_ROOT=/app \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    LOG_LEVEL=INFO \
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    CONTENT_SERVICE_URL=http://content_service:8000/v1/content \
    SERVICE_NAME=nlp_service

RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pdm

WORKDIR /app

FROM base AS deps-base

COPY pyproject.toml pdm.lock ./
COPY libs/common_core/pyproject.toml libs/common_core/pyproject.toml
COPY libs/common_core/src/ libs/common_core/src/
COPY libs/huleedu_service_libs/pyproject.toml libs/huleedu_service_libs/pyproject.toml
COPY libs/huleedu_service_libs/src/ libs/huleedu_service_libs/src/
COPY libs/huleedu_nlp_shared/pyproject.toml libs/huleedu_nlp_shared/pyproject.toml
COPY libs/huleedu_nlp_shared/src/ libs/huleedu_nlp_shared/src/

COPY services/api_gateway_service/pyproject.toml services/api_gateway_service/pyproject.toml
COPY services/batch_conductor_service/pyproject.toml services/batch_conductor_service/pyproject.toml
COPY services/batch_orchestrator_service/pyproject.toml services/batch_orchestrator_service/pyproject.toml
COPY services/cj_assessment_service/pyproject.toml services/cj_assessment_service/pyproject.toml
COPY services/class_management_service/pyproject.toml services/class_management_service/pyproject.toml
COPY services/content_service/pyproject.toml services/content_service/pyproject.toml
COPY services/email_service/pyproject.toml services/email_service/pyproject.toml
COPY services/entitlements_service/pyproject.toml services/entitlements_service/pyproject.toml
COPY services/essay_lifecycle_service/pyproject.toml services/essay_lifecycle_service/pyproject.toml
COPY services/file_service/pyproject.toml services/file_service/pyproject.toml
COPY services/identity_service/pyproject.toml services/identity_service/pyproject.toml
COPY services/language_tool_service/pyproject.toml services/language_tool_service/pyproject.toml
COPY services/llm_provider_service/pyproject.toml services/llm_provider_service/pyproject.toml
COPY services/nlp_service/pyproject.toml services/nlp_service/pyproject.toml
COPY services/result_aggregator_service/pyproject.toml services/result_aggregator_service/pyproject.toml
COPY services/spellchecker_service/pyproject.toml services/spellchecker_service/pyproject.toml
COPY services/websocket_service/pyproject.toml services/websocket_service/pyproject.toml

FROM deps-base AS deps-prod
RUN pdm install --prod --frozen-lockfile

FROM base AS runtime

COPY --from=deps-prod /app /app
COPY services/nlp_service/ /app/services/nlp_service/

RUN groupadd -r nlpuser && useradd --no-log-init -r -g nlpuser nlpuser \
    && chown -R nlpuser:nlpuser /app

USER nlpuser
WORKDIR /app

CMD ["pdm", "run", "-p", "/app", "python", "services/nlp_service/worker_main.py"]
