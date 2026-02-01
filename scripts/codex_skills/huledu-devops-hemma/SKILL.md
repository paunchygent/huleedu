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

Example (service rebuild/restart):
```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose -f docker-compose.hemma.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml up -d --build language_tool_service'
```

Embedding offload deploy (ROCm/HIP, localhost-only, compose profile):
```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose -f docker-compose.hemma.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml --profile research-offload up -d --build essay_embed_offload'
```

Embedding offload deploy (script alternative; handles docker-snap mount workarounds):
```bash
ssh hemma 'cd ~/apps/huleedu && ./scripts/ml_training/essay_scoring/offload/hemma_offload_deploy.sh'
```
