---
type: runbook
service: global
severity: high
last_reviewed: '2026-02-01'
---
# GPU AI Workloads on Hemma (HuleEdu)

## Symptoms

- GPU-backed container is up but inference is slow (CPU fallback).
- Container can’t see GPU devices.
- ROCm tools missing on host or inside container.
- Model weights are re-downloaded repeatedly (cache not mounted).

## Diagnosis

### Host-level GPU visibility (Hemma)

Run on Hemma:

```bash
ssh hemma 'rocminfo | head'
ssh hemma 'rocm-smi || true'
```

If these don’t exist, ROCm is not installed or not in PATH.

### Device nodes (Hemma)

```bash
ssh hemma 'ls -la /dev/kfd /dev/dri || true'
```

### Container-level verification (ROCm torch)

```bash
ssh hemma 'sudo docker exec -it <container_name> python -c \"import torch; print(torch.cuda.is_available()); print(getattr(torch.version, \\\"hip\\\", None))\"'
```

Interpretation:
- `torch.cuda.is_available() == True` typically indicates GPU availability.
- `torch.version.hip` should be non-null on ROCm-enabled torch builds.

## Resolution

### Prefer non-snap Docker on Hemma (recommended)

If `docker` is snap-installed on Hemma, host path mounts outside `$HOME` can be
restricted (often breaking mounts from `/srv/*`). For HuleEdu we want predictable,
data-disk-backed caches mounted directly from `/srv/scratch/...`, so a non-snap Docker
Engine install is the most maintainable steady-state.

Detect docker-snap:
```bash
ssh hemma 'command -v docker && ls -la "$(command -v docker)"'
ssh hemma 'snap list docker || true'
```

If docker-snap is installed, migrate to Docker Engine using Docker’s official host
install docs for your OS (Ubuntu is the common case). Verify mounts work by starting a
container with a `/srv/scratch/...` bind mount and checking it reads/writes as expected.

### Standardize GPU workloads as Docker services

Run Hemma workloads via Docker so they’re reproducible and easy to operate:
- stable ports + health endpoints
- restart/redeploy via compose
- explicit volumes for caches

For the DeBERTa + spaCy feature offload service, ensure:
- persistent Hugging Face cache volume is mounted
- spaCy model assets are mounted or baked into the image
- the container runs with ROCm-visible devices and permissions
- `OFFLOAD_TORCH_DEVICE` is set appropriately (often `cuda` on ROCm-enabled torch builds)

Recommended base image (Hemma, AMD ROCm):
- `rocm/pytorch:latest`

Important:
- Avoid installing `torch` via pip during the image build if the base image already provides a ROCm-enabled torch build. Otherwise, you can accidentally replace it with a non-ROCm wheel.

### Confirm caching works

After the first run, verify the cache volume contains model artifacts and subsequent
runs do not re-download weights.

## Prevention

- Mount explicit cache volumes for:
  - Hugging Face model weights
  - spaCy models
  - any server-side feature caches (if added)
- Prefer binary responses for embedding vectors to minimize bandwidth/CPU overhead.
- Keep this runbook scoped to steady-state GPU operations (GPU stability issues are
  considered solved on Hemma and are intentionally out of scope here).
