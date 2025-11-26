# Auto-generated production Dockerfile for identity_service
ARG DEPS_IMAGE=huledu-deps:dev
FROM ${DEPS_IMAGE} AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PDM_USE_VENV=false \
    PDM_IGNORE_ACTIVE_VENV=1 \
    PROJECT_ROOT=/app \
    PYTHONPATH=/app \
    ENV_TYPE=docker

WORKDIR /app

FROM base AS production
COPY --chown=appuser:appuser services/identity_service/ /app/services/identity_service/
USER appuser
WORKDIR /app
CMD ["sh", "-c", "pdm run -p /app python -m hypercorn services.identity_service.app:app --bind 0.0.0.0:${IDENTITY_SERVICE_HTTP_PORT:-7005}"]
