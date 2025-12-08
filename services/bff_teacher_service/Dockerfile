# BFF Teacher Service Dockerfile
# Multi-stage build: Node.js builds frontend, Python serves static files

# Global ARG must be before any FROM to be available to all stages
ARG DEPS_IMAGE=huledu-deps:dev

# ============================================================================
# Stage 1: Frontend Builder (Node.js + pnpm)
# Used by CI/production builds. Dev uses volume mount instead.
# ============================================================================
FROM node:20-slim AS frontend-builder

# Enable pnpm via corepack
RUN corepack enable pnpm

WORKDIR /frontend

# Copy package files first for layer caching
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Copy source and build
COPY frontend/ ./
RUN pnpm build

# ============================================================================
# Stage 2: Python Base (huledu-deps pattern)
# Re-declare ARG after FROM to access global ARG value
# ============================================================================
ARG DEPS_IMAGE
FROM ${DEPS_IMAGE} AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PDM_USE_VENV=false \
    PDM_IGNORE_ACTIVE_VENV=1 \
    PROJECT_ROOT=/app \
    PYTHONPATH=/app \
    ENV_TYPE=docker

WORKDIR /app

# ============================================================================
# Stage 3: Production
# ============================================================================
FROM base AS production

# Copy service code
COPY --chown=appuser:appuser services/bff_teacher_service/ /app/services/bff_teacher_service/

# Copy frontend build from builder stage
# This is overridden by volume mount in dev compose
COPY --from=frontend-builder --chown=appuser:appuser /frontend/dist /app/static

USER appuser
WORKDIR /app

# Run with uvicorn
CMD ["pdm", "run", "-p", "/app", "python", "-m", "uvicorn", "services.bff_teacher_service.app:app", "--host", "0.0.0.0", "--port", "4101"]
