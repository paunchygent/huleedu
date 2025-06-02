# Multi-stage Dockerfile for CJ Assessment Service
FROM python:3.11-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install PDM
RUN pip install --no-cache-dir pdm

# Copy dependency files
COPY pyproject.toml pdm.lock ./

# Copy common_core and service_libs 
COPY common_core/ ./common_core/
COPY services/libs/ ./services/libs/

# Install dependencies
RUN pdm install --check --prod

# Copy service source code
COPY services/cj_assessment_service/ ./services/cj_assessment_service/

# Production stage
FROM base AS production

# Create non-root user
RUN groupadd -r cjassessment && useradd -r -g cjassessment cjassessment
USER cjassessment

# Set service environment
ENV PYTHONPATH=/app/services/cj_assessment_service
ENV SERVICE_NAME=cj_assessment_service

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9090/health || exit 1

# Default command (runs worker)
WORKDIR /app/services/cj_assessment_service
CMD ["pdm", "run", "start_worker"] 