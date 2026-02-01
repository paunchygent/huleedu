# Research-scoped DeBERTa embedding offload server.
#
# Notes:
# - Default base image is ROCm-enabled for Hemma (canonical: rocm/pytorch:latest).
#   Override BASE_IMAGE only if you know the base provides a compatible `torch`.
# - Uses the minimal `offload-runtime` dependency group (not `ml-research`) so Hemma
#   runtime images don't pull training-only deps (e.g. XGBoost/SHAP/spaCy).
# - We intentionally do NOT install `torch*` via pip; the base image is authoritative.
ARG BASE_IMAGE=rocm/pytorch:latest
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

# Sanity: base image must provide torch (ROCm torch reports as torch.cuda + torch.version.hip).
RUN python -c "import torch; print('torch', torch.__version__); print('hip', getattr(torch.version, 'hip', None)); print('cuda_is_available', torch.cuda.is_available())"

# Install locked deps from `offload-runtime` only (exclude root `default` deps).
#
# The base image provides torch; this layer only installs the Python deps needed for
# the offload server and DeBERTa tokenization/model loading.
RUN pdm export --no-default -G offload-runtime -f requirements --without-hashes -o /tmp/requirements.txt && \
    # Drop NVIDIA/CUDA packages if they appear (bloat + wrong hardware intent).
    grep -Ev '^nvidia[-_]' /tmp/requirements.txt \
      | grep -Ev '^cuda[-_]' \
      | grep -Ev '^triton\b' \
      > /tmp/requirements.filtered.txt && \
    python -m pip install --no-cache-dir -r /tmp/requirements.filtered.txt

EXPOSE 9000

CMD ["python", "-m", "scripts.ml_training.essay_scoring.offload.server"]
