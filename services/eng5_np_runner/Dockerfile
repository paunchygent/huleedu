# Auto-generated production Dockerfile for eng5_np_runner
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
COPY --chown=appuser:appuser scripts/cj_experiments_runners/ /app/scripts/cj_experiments_runners/
USER appuser
WORKDIR /app
ENTRYPOINT ["pdm", "run", "-p", "/app", "eng5-np-run"]
CMD ["--help"]
