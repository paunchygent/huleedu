# Multi-stage build for optimized production image
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PDM_USE_VENV=false

# Install build dependencies including tools for downloading LanguageTool
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    build-essential \
    python3-dev \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install PDM
RUN pip install --no-cache-dir pdm

# Download LanguageTool
RUN mkdir -p /app/languagetool && \
    cd /app/languagetool && \
    wget -q https://languagetool.org/download/LanguageTool-stable.zip && \
    unzip -q LanguageTool-stable.zip && \
    mv LanguageTool-*/*.jar . && \
    rm -rf LanguageTool-* LanguageTool-stable.zip

# Set working directory
WORKDIR /app

# Copy shared local dependencies
COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/

# Copy service files
COPY services/language_tool_service/ /app/services/language_tool_service/

# Switch to service directory and install dependencies
WORKDIR /app/services/language_tool_service
COPY pdm.lock /app/services/language_tool_service/pdm.lock
RUN pdm install --prod --frozen-lockfile

# Final runtime stage
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    LANGUAGE_TOOL_SERVICE_LOG_LEVEL=INFO \
    LANGUAGE_TOOL_SERVICE_PORT=8085 \
    LANGUAGE_TOOL_SERVICE_HOST=0.0.0.0 \
    PDM_USE_VENV=false

# Install Java 21 JRE and other runtime dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    openjdk-21-jre-headless \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install PDM in runtime (needed for pdm run command)
RUN pip install --no-cache-dir pdm

# Create application directory
WORKDIR /app

# Copy the built application and dependencies from builder stage
COPY --from=builder /app /app

# Create user and set permissions
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser \
    && chown -R appuser:appuser /app

USER appuser
WORKDIR /app/services/language_tool_service

# Expose the service port
EXPOSE ${LANGUAGE_TOOL_SERVICE_PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8085/healthz || exit 1

# Command to run the service
CMD ["pdm", "run", "start"]