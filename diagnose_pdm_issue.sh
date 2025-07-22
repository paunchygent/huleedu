#!/bin/bash

echo "Diagnosing PDM segmentation fault issue..."

# Option 1: Test with specific PDM version
echo "=== Option 1: Pin PDM version ==="
cat > services/file_service/Dockerfile.test1 << 'EOF'
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PDM_USE_VENV=false

WORKDIR /app

# Install specific PDM version that might be more stable
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir pdm==2.12.4

COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/
COPY services/file_service/ /app/services/file_service/

WORKDIR /app/services/file_service
RUN pdm install --prod

CMD ["pdm", "run", "start"]
EOF

# Option 2: Test with --no-lock to skip lock file generation
echo "=== Option 2: Use pdm install --no-lock ==="
cat > services/file_service/Dockerfile.test2 << 'EOF'
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PDM_USE_VENV=false

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir pdm

COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/
COPY services/file_service/ /app/services/file_service/

WORKDIR /app/services/file_service
# Skip lock file generation entirely
RUN pdm install --prod --no-lock

CMD ["pdm", "run", "start"]
EOF

# Option 3: Test with pip instead of pdm for production
echo "=== Option 3: Export requirements and use pip ==="
cat > services/file_service/Dockerfile.test3 << 'EOF'
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/
COPY services/file_service/ /app/services/file_service/

WORKDIR /app/services/file_service

# First install PDM just to export requirements
RUN pip install --no-cache-dir pdm && \
    pdm export --prod -f requirements > requirements.txt && \
    pip uninstall -y pdm && \
    pip install --no-cache-dir -r requirements.txt && \
    rm requirements.txt

CMD ["hypercorn", "app:app", "--config", "python:hypercorn_config"]
EOF

echo "Test Dockerfiles created. You can test each approach with:"
echo "  docker build -f services/file_service/Dockerfile.test1 -t file_service_test1 ."
echo "  docker build -f services/file_service/Dockerfile.test2 -t file_service_test2 ."
echo "  docker build -f services/file_service/Dockerfile.test3 -t file_service_test3 ."