---
name: huledu-devops-hemma
description: >
  DevOps and server management for running HuleEdu services and GPU-backed NLP
  workloads on Hemma (hemma.hule.education). Covers LanguageTool service,
  DeBERTa/spaCy feature offload, tunnels, and coexistence with Skriptoteket.
---

# HuleEdu DevOps (Hemma)

Source of truth in this repo:
- Home server ops: `docs/operations/hemma-server-operations-huleedu.md`
- GPU workloads: `docs/operations/gpu-ai-workloads-on-hemma-huleedu.md`
- Architecture decision: `docs/decisions/0025-hemma-hosted-nlp-feature-offload-for-essay-scoring-research-binary-protocol.md`

Non-goals:
- Do not include “GPU hard hang / freeze” troubleshooting (Hemma GPU stability is assumed solved).
- Do not expose Hemma localhost-only services publicly; default to tunnels.

## SSH (Mac → Hemma)

Assumption: you have SSH host aliases configured locally (e.g. `hemma`, `hemma-root`).
Default to non-root SSH and use root only when explicitly asked.

## Tunnels (default transport)

LanguageTool service (HuleEdu API):
```bash
ssh hemma -L 18085:127.0.0.1:8085 -N
curl -fsS http://127.0.0.1:18085/healthz
```

DeBERTa + spaCy feature offload service:
```bash
ssh hemma -L 19000:127.0.0.1:9000 -N
curl -fsS http://127.0.0.1:19000/healthz
```

Transformer fine-tuning note:
- Gate G3 training must run in the dedicated container `huleedu_essay_transformer_train`
  (compose profile `research-transformer-train`), not from host Python.

## Long-running research runs (Mac)

If a run “stops without errors” and Hemma containers are idle, the most common cause is the Mac-side
client process being terminated by session teardown (closing the terminal tab, tool runner cleanup).

Preferred:
- Run from a dedicated terminal session started via `./scripts/dev-shell.sh`.
- For detached runs on macOS, use `/usr/bin/screen`:
  - Start: `/usr/bin/screen -S essay_scoring_run -dm /bin/bash -lc '<command>'`
  - Attach: `/usr/bin/screen -r essay_scoring_run`

## Hemma: quick triage commands

Docker install sanity (snap vs non-snap):
```bash
ssh hemma 'command -v docker && ls -la "$(command -v docker)"'
ssh hemma 'snap list docker || true'
```

Containers:
```bash
ssh hemma 'sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
```

LanguageTool logs:
```bash
ssh hemma 'sudo docker logs --tail=200 -f huleedu_language_tool_service'
```

## Throughput + bottlenecks (Hemma offload)

Canonical per-run client metrics:
- `output/essay_scoring/<RUN>/artifacts/offload_metrics.json`
  - headline: `benchmarks[].essays_per_second`
  - Hemma backend mode (`/v1/extract`): focus on `offload.extract.requests.latency_s` + request counts

Primary Hemma-side tuning knobs (no quality reduction):
- LanguageTool service:
  - `LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS`
  - `LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_HEAP_SIZE`
  - `WEB_CONCURRENCY` (Hypercorn workers; increases RAM)
- Offload server:
  - `OFFLOAD_HTTP_MAX_WORKERS`
  - `OFFLOAD_LANGUAGE_TOOL_MAX_CONCURRENCY`
  - `OFFLOAD_EMBEDDING_BATCH_SIZE`
  - `OFFLOAD_SPACY_N_PROCESS`, `OFFLOAD_SPACY_PIPE_BATCH_SIZE`

## GPU verification (ROCm)

Host tools:
```bash
ssh hemma 'rocminfo | head'
ssh hemma 'rocm-smi || true'
```

Container torch check:
```bash
ssh hemma 'sudo docker exec -it <container_name> python -c "import torch; print(torch.cuda.is_available()); print(getattr(torch.version, \"hip\", None))"'
```

## Deploy/redeploy pattern (template)

Canonical Hemma checkout location (mirror Skriptoteket):
- `~/apps/huleedu`

Note: The local repo you are working from may still be named `huledu-reboot`, but Hemma
should standardize on the future canonical repo name and path: `~/apps/huleedu`.

Repo sync rule:
- Use `git pull` on Hemma for tracked files.
- Do **not** use `scp` to “sync” repo code (it creates drift). `scp` is only acceptable
  for non-versioned secrets/artifacts (for example `.env`).

## SSH command pattern (avoid quoting issues)

Canonical repo root on Hemma:
- `/home/paunchygent/apps/huleedu`

One-liner:
```bash
ssh hemma /bin/bash -c 'cd /home/paunchygent/apps/huleedu && ./scripts/validate-production-config.sh'
```

Multi-line (preferred when commands contain quotes/braces/pipes):
```bash
ssh hemma /bin/bash -s <<'EOF'
set -euo pipefail
cd /home/paunchygent/apps/huleedu
./scripts/validate-production-config.sh
sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
EOF
```

Example (service rebuild/restart):
```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose -f docker-compose.hemma.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml up -d --build language_tool_service'
```

Embedding offload deploy (ROCm/HIP, localhost-only, compose profile):
```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose -f docker-compose.hemma.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml --profile research-offload up -d --build essay_embed_offload'
```

Transformer training runtime deploy (ROCm/HIP, profile-gated):
```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml --profile research-transformer-train up -d --build essay_transformer_train'
```

Training runtime preflight:
```bash
ssh hemma 'sudo docker exec huleedu_essay_transformer_train python - <<\"PY\"\nimport torch\nprint(torch.cuda.is_available(), getattr(torch.version, \"hip\", None))\nPY'
ssh hemma 'sudo docker exec huleedu_essay_transformer_train /bin/bash -lc \"cd /app && /opt/venv/bin/pdm run essay-scoring-research transformer-finetune --help >/dev/null\"'
```

Canonical G3 detached launch (from local repo root):
```bash
pdm run g3-launch-hemma
```

Embedding offload deploy (script alternative; handles docker-snap mount workarounds):
```bash
ssh hemma 'cd ~/apps/huleedu && ./scripts/ml_training/essay_scoring/offload/hemma_offload_deploy.sh'
```
