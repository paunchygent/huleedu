#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname "$0")/../../../../.." && pwd)"

IMAGE_TAG="${IMAGE_TAG:-huleedu-essay-embed-offload:dev}"
CONTAINER_NAME="${CONTAINER_NAME:-huleedu-embed-offload}"
BASE_IMAGE="${BASE_IMAGE:-rocm/pytorch:latest}"
HOST_BIND="${HOST_BIND:-127.0.0.1}"
PORT="${PORT:-9000}"

DATA_ROOT="${DATA_ROOT:-/srv/scratch/huleedu}"
HF_CACHE_HOST="${HF_CACHE_HOST:-$DATA_ROOT/cache/huggingface}"

echo "== HuleEdu DeBERTa offload (ROCm/HIP) deploy =="
echo "repo_root=$REPO_ROOT"
echo "image_tag=$IMAGE_TAG"
echo "container_name=$CONTAINER_NAME"
echo "base_image=$BASE_IMAGE"
echo "bind=$HOST_BIND:$PORT"
echo "hf_cache_host=$HF_CACHE_HOST"
echo

echo "== Stop any ROCm llama.cpp container (VRAM) =="
if sudo /snap/bin/docker ps --format '{{.Names}}' | grep -qx "llama-server-rocm"; then
  sudo /snap/bin/docker update --restart=no llama-server-rocm >/dev/null 2>&1 || true
  sudo /snap/bin/docker stop llama-server-rocm
fi

echo "== Update repo (ff-only) =="
cd "$REPO_ROOT"
git pull --ff-only

echo "== Ensure HF cache dir on data disk =="
sudo mkdir -p "$HF_CACHE_HOST"
sudo chown -R "$(id -u):$(id -g)" "$DATA_ROOT" || true

echo "== Build image =="
sudo /snap/bin/docker build \
  -f scripts/ml_training/essay_scoring/offload/Dockerfile \
  --build-arg "BASE_IMAGE=$BASE_IMAGE" \
  -t "$IMAGE_TAG" \
  .

echo "== Run container =="
sudo /snap/bin/docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
sudo /snap/bin/docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -p "$HOST_BIND:$PORT:$PORT" \
  --device=/dev/kfd \
  --device=/dev/dri \
  --group-add video \
  --ipc=host \
  --shm-size 8g \
  -e HF_HOME=/cache/huggingface \
  -e TRANSFORMERS_CACHE=/cache/huggingface \
  -v "$HF_CACHE_HOST:/cache/huggingface" \
  "$IMAGE_TAG"

echo "== Wait for healthz =="
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -fsS "http://127.0.0.1:$PORT/healthz"
echo

echo "== GPU sanity (ROCm/HIP uses torch.cuda) =="
sudo /snap/bin/docker exec "$CONTAINER_NAME" python - <<'PY'
import torch

print("torch", torch.__version__)
print("torch.version.hip", getattr(torch.version, "hip", None))
print("torch.cuda.is_available()", torch.cuda.is_available())
print("torch.cuda.device_count()", torch.cuda.device_count())

if torch.cuda.is_available():
    x = torch.randn((256, 256), device="cuda")
    print("cuda_tensor_mean", float(x.mean()))
PY

echo "== Done =="

