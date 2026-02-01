# Research-scoped DeBERTa embedding offload server.
#
# Notes:
# - Default base image is CPU-only. On Hemma, override BASE_IMAGE to a ROCm-enabled
#   PyTorch image for GPU inference (canonical: rocm/pytorch:latest).
# - Uses `pdm install -G ml-research` so dependencies match the research pipeline.
# - We intentionally do NOT install `torch*` via PDM/pip when using a ROCm base image,
#   to avoid clobbering the ROCm-enabled torch bundled in that image.
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PDM_USE_VENV=false \
    PDM_IGNORE_ACTIVE_VENV=1 \
    PROJECT_ROOT=/app \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pdm

COPY pyproject.toml pdm.lock ./
COPY scripts/__init__.py scripts/__init__.py
COPY scripts/ml_training/__init__.py scripts/ml_training/__init__.py
COPY scripts/ml_training/essay_scoring/ scripts/ml_training/essay_scoring/

# Install locked deps from `ml-research`, but exclude torch* so the base image stays authoritative.
RUN pdm export -G ml-research -f requirements --without-hashes -o /tmp/requirements.txt && \
    grep -Ev '^(torch|torchvision|torchaudio)==.*$' /tmp/requirements.txt > /tmp/requirements.no-torch.txt && \
    python -m pip install --no-cache-dir -r /tmp/requirements.no-torch.txt

# Quick sanity printout (helpful in build logs on Hemma).
RUN python -c "import torch; print('torch', torch.__version__); print('hip', getattr(torch.version, 'hip', None)); print('cuda_is_available', torch.cuda.is_available())"

EXPOSE 9000

CMD ["pdm", "run", "-p", "/app", "python", "-m", "scripts.ml_training.essay_scoring.offload.server"]
