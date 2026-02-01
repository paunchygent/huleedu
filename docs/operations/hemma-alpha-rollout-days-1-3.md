---
type: runbook
service: global
severity: high
last_reviewed: '2026-02-01'
---
# Hemma alpha rollout (Days 1-3)

Executable rollout steps for making HuleEdu publicly reachable on Hemma (DNS/TLS +
nginx-proxy routing) and establishing the first repeatable “git pull + compose up”
deployment workflow.

This runbook intentionally focuses on Days 1–3 of:
- `TASKS/programs/huledu_alpha_launch/hub.md`

## Preconditions

- Hemma already runs the shared reverse proxy stack (nginx-proxy + Let’s Encrypt) used
  by Skriptoteket.
- An external Docker network exists for cross-app routing (called `hule-network` in the
  HuleEdu repo).
- You can SSH to Hemma as non-root.

## Day 1 — DNS + TLS surface (public)

### 1. DNS records

Create/verify public DNS A/AAAA records pointing to Hemma’s public IP:
- `api.huleedu.hule.education`
- `huleedu.hule.education`
- `ws.huleedu.hule.education`

Verify from your dev machine:
```bash
dig +short api.huleedu.hule.education
dig +short huleedu.hule.education
dig +short ws.huleedu.hule.education
```

### 2. Reverse proxy stack health

Verify that Hemma’s proxy stack is running and listening on 80/443:
```bash
ssh hemma 'sudo ss -lntp | rg \":(80|443)\" || true'
ssh hemma 'sudo docker ps --format \"table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\" | rg -i \"nginx|proxy|letsencrypt\" || true'
```

### 3. Certificate issuance readiness

We rely on nginx-proxy auto-discovery (container env vars). HuleEdu production overrides
already declare:
- `VIRTUAL_HOST`
- `VIRTUAL_PORT`
- `LETSENCRYPT_HOST`

See `docker-compose.prod.yml` in this repo for the authoritative hostnames.

## Day 2 — First HuleEdu deploy workflow on Hemma

### 0. Decide the Hemma checkout location

There is no canonical path yet. Choose one and treat it as a constant once chosen.
All commands below use:

- `<HULEDU_REPO_ON_HEMMA>` (absolute path)

### 1. Create external network (once)

HuleEdu production overrides assume an external network:
```bash
ssh hemma 'sudo docker network create hule-network || true'
ssh hemma 'sudo docker network ls | rg \"\\bhule-network\\b\"'
```

### 2. Mirror the repo on Hemma

First-time setup (example):
```bash
ssh hemma 'mkdir -p <HULEDU_REPO_ON_HEMMA_PARENT>'
ssh hemma 'cd <HULEDU_REPO_ON_HEMMA_PARENT> && git clone <YOUR_GIT_REMOTE> huledu-reboot'
```

Subsequent updates:
```bash
ssh hemma 'cd <HULEDU_REPO_ON_HEMMA> && git pull'
```

### 3. Create Hemma `.env` for production

`docker-compose.prod.yml` documents required variables at the top of the file. At
minimum you will need the production DB password, JWT secret, and internal API key.

Create/edit:
```bash
ssh hemma 'cd <HULEDU_REPO_ON_HEMMA> && nano .env'
```

### 4. Shared DB prerequisites (if using shared-postgres)

`docker-compose.prod.yml` includes the SQL block needed to create databases in
`shared-postgres`.

Run on Hemma:
```bash
ssh hemma 'sudo docker exec -it shared-postgres psql -U postgres -c \"\\l\"'
```

(Optional) create missing databases (copy the SQL block from `docker-compose.prod.yml`).

### 5. First deploy (build + start)

Use prod overrides on top of base compose:
```bash
ssh hemma 'cd <HULEDU_REPO_ON_HEMMA> && sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build'
```

### 6. Verify service health (container-level)

```bash
ssh hemma 'cd <HULEDU_REPO_ON_HEMMA> && sudo docker compose ps'
```

Health endpoints inside the stack (examples; adjust ports if configured differently):
```bash
ssh hemma 'curl -fsS http://127.0.0.1:8080/healthz || true'   # api gateway if bound to host
ssh hemma 'curl -fsS http://127.0.0.1:4101/healthz || true'   # bff
```

### 7. Verify reverse proxy routing + TLS

From your dev machine:
```bash
curl -fsSI https://api.huleedu.hule.education/healthz
curl -fsSI https://huleedu.hule.education/healthz
curl -fsSI https://ws.huleedu.hule.education/healthz
```

If TLS issuance is still pending, tail the proxy logs on Hemma until cert provisioning
completes.

## Day 3 — `language_tool_service` on Hemma for research (tunneled)

We deploy HuleEdu’s `language_tool_service` in Docker and keep it localhost-only on
Hemma, then tunnel it to the dev machine.

### 1. Deploy language_tool_service

If the main HuleEdu stack is up, the service may already be running. Verify first:
```bash
ssh hemma 'sudo docker ps --format \"table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\" | rg \"language_tool\" || true'
```

### 2. Health check on Hemma (localhost)

```bash
ssh hemma 'curl -fsS http://127.0.0.1:8085/healthz'
```

### 3. Tunnel to local port (recommended: autossh)

Install autossh on macOS:
```bash
brew install autossh
```

Start tunnel:
```bash
autossh -M 0 -N \
  -o \"ServerAliveInterval=30\" \
  -o \"ServerAliveCountMax=3\" \
  -o \"ExitOnForwardFailure=yes\" \
  -L 18085:localhost:8085 hemma
```

Verify locally:
```bash
curl -fsS http://127.0.0.1:18085/healthz
```

### 4. Smoke test `POST /v1/check`

```bash
curl -fsS http://127.0.0.1:18085/v1/check \
  -H 'Content-Type: application/json' \
  -d '{\"text\":\"This are bad.\",\"language\":\"en-US\"}' | head
```

## Day 3 (optional) — DeBERTa embedding offload server (tunneled)

This is the research-scoped embedding server under:
- `scripts/ml_training/essay_scoring/offload/`

It returns embeddings as a binary `.npy` float32 matrix for throughput.

### 1. Build the image on Hemma

CPU-only (works everywhere, but is not GPU accelerated):
```bash
ssh hemma 'cd <HULEDU_REPO_ON_HEMMA> && sudo docker build -f scripts/ml_training/essay_scoring/offload/Dockerfile -t huleedu-essay-embed-offload:dev .'
```

GPU (ROCm) build: override `BASE_IMAGE` to a ROCm-enabled PyTorch image available on Hemma.
```bash
ssh hemma 'cd <HULEDU_REPO_ON_HEMMA> && sudo docker build -f scripts/ml_training/essay_scoring/offload/Dockerfile --build-arg BASE_IMAGE=rocm/pytorch:latest -t huleedu-essay-embed-offload:dev .'
```

### 2. Run the container (localhost-only on Hemma)

```bash
ssh hemma 'sudo docker rm -f huleedu_essay_embed_offload || true'
ssh hemma 'sudo docker run -d --name huleedu_essay_embed_offload --restart unless-stopped \
  -p 127.0.0.1:9000:9000 \
  -e OFFLOAD_HTTP_PORT=9000 \
  -e OFFLOAD_TORCH_DEVICE=${OFFLOAD_TORCH_DEVICE:-cuda} \
  -v huleedu_hf_cache:/root/.cache/huggingface \
  huleedu-essay-embed-offload:dev'
```

### 3. Health check on Hemma

```bash
ssh hemma 'curl -fsS http://127.0.0.1:9000/healthz'
```

### 4. Tunnel to local port

```bash
autossh -M 0 -N \
  -o \"ServerAliveInterval=30\" \
  -o \"ServerAliveCountMax=3\" \
  -o \"ExitOnForwardFailure=yes\" \
  -L 19000:localhost:9000 hemma
```

Verify locally:
```bash
curl -fsS http://127.0.0.1:19000/healthz
```

### 5. Run the research pipeline against Hemma

Example:
```bash
pdm run essay-scoring-research ablation \
  --dataset-path /tmp/ielts_small_ablation.csv \
  --language-tool-service-url http://127.0.0.1:18085 \
  --embedding-service-url http://127.0.0.1:19000
```

## Notes

- Keep “public” surface area limited to the three entrypoint domains (API/BFF/WS).
- Keep heavy research/offload endpoints localhost-only on Hemma and accessed via tunnels.

## Symptoms

## Diagnosis

## Resolution

## Prevention
