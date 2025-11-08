# Auto-generated production Dockerfile for email_service
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
COPY --chown=appuser:appuser services/email_service/ /app/services/email_service/
USER appuser
WORKDIR /app
CMD ["pdm", "run", "-p", "/app", "python", "-m", "hypercorn", "services.email_service.app:app", "--bind", "0.0.0.0:8080"]
