# Dockerfile for Result Aggregator Service
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy service files
COPY pyproject.toml pdm.lock ./
COPY services/result_aggregator_service ./services/result_aggregator_service
COPY common_core ./common_core
COPY services/libs ./services/libs

# Install PDM and dependencies
RUN pip install pdm && \
    pdm install --prod --no-lock

# Set Python path
ENV PYTHONPATH=/app

# Expose ports
EXPOSE 4003 9096

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:4003/healthz || exit 1

# Run the service
CMD ["pdm", "run", "python", "-m", "services.result_aggregator_service.app"]