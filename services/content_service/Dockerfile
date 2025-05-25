FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    LOG_LEVEL=INFO \
    CONTENT_STORE_ROOT_PATH=/data/huleedu_content_store \
    PORT=8000

WORKDIR /app

# Install PDM
RUN pip install --no-cache-dir pdm

# Copy only build files from repo root context
COPY services/content_service/pyproject.toml services/content_service/pdm.lock ./

# Install dependencies --no-editable to ensure it fetches from remote if common_core is published
# Or, if common_core is local, adjust pdm install to find it or copy its wheel.
RUN pdm install --prod --no-editable

# Copy the rest of the application code
COPY services/content_service/ ./

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    mkdir -p ${CONTENT_STORE_ROOT_PATH} && \
    chown -R appuser:appuser ${CONTENT_STORE_ROOT_PATH} && \
    chown -R appuser:appuser /app
USER appuser

# Expose the port the app runs on
EXPOSE ${PORT}

# Command to run the application
CMD ["pdm", "run", "start"] 