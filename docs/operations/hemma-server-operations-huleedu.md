---
type: runbook
service: global
severity: high
last_reviewed: '2026-02-01'
---
# Hemma Server Operations (HuleEdu)

## Symptoms

Common signals that Hemma-hosted HuleEdu infra is unhealthy:

- SSH unreachable / tunnel won’t connect
- `language_tool_service` health check fails (`/healthz`)
- DeBERTa/spaCy offload service health check fails (`/healthz`)
- Requests time out from the Mac research pipeline while fetching features
- Reverse-proxied hostnames (for example `skriptoteket.hule.education`) return 502/504

## Diagnosis

Prefer “prove current state” over assumptions.

## Command Hygiene (Hemma)

When running commands over SSH, always include an explicit `cd` to the repo root in
the same SSH invocation. Do not assume any working directory persists between
commands.

Canonical repo path on Hemma:
- `/home/paunchygent/apps/huleedu`

### SSH one-liner pattern (safe)

```bash
ssh hemma /bin/bash -c 'cd /home/paunchygent/apps/huleedu && ./scripts/validate-production-config.sh'
```

### SSH multi-line pattern (avoid quoting issues)

Prefer this for any sequence that includes quotes, braces, pipes, or here-docs:

```bash
ssh hemma /bin/bash -s <<'EOF'
set -euo pipefail
cd /home/paunchygent/apps/huleedu
./scripts/validate-production-config.sh
sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
EOF
```

### SSH + host reachability

```bash
ssh hemma 'uptime'
```

### Docker binary sanity (snap vs non-snap)

For HuleEdu we prefer a non-snap Docker Engine install on Hemma for predictable host
mount behavior from `/srv/scratch/...`.

```bash
ssh hemma 'command -v docker && ls -la "$(command -v docker)"'
ssh hemma 'snap list docker || true'
```

### Docker sanity

```bash
ssh hemma 'sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
```

### Service health checks (localhost on Hemma)

LanguageTool service (HuleEdu API):
```bash
ssh hemma 'curl -fsS http://127.0.0.1:8085/healthz'
```

Feature offload service (DeBERTa + spaCy; if deployed):
```bash
ssh hemma 'curl -fsS http://127.0.0.1:9000/healthz'
```

Current implementation note:
- The initial offload server is embedding-focused (`POST /v1/embed` returning `.npy`).
- Source: `scripts/ml_training/essay_scoring/offload/`

### Logs (container-level)

```bash
ssh hemma 'sudo docker logs --tail=200 -f huleedu_language_tool_service'
```

Embedding offload server logs (if deployed via `docker run`):
```bash
ssh hemma 'sudo docker logs --tail=200 -f huleedu_essay_embed_offload'
```

## Resolution

### Hemma `.env` sanity (required for prod)

On Hemma, keep secrets in `~/apps/huleedu/.env` (never committed). Required keys for
the shared-infra production deploy:
- `HULEEDU_ENVIRONMENT=production`
- `ENVIRONMENT=production`
- `HULEEDU_DB_USER=...`
- `HULEEDU_PROD_DB_PASSWORD=...` (password for `shared-postgres`)
- `HULEEDU_INTERNAL_API_KEY=...`
- `JWT_SECRET_KEY=...` (and optionally `API_GATEWAY_JWT_SECRET_KEY`, matching it)
- `HF_TOKEN=...` (recommended for DeBERTa offload image pulls; avoids Hub rate limits)

Validate on Hemma (prints missing keys only):
```bash
ssh hemma 'cd ~/apps/huleedu && ./scripts/validate-production-config.sh'
```

### SSH port-forward tunnels (default)

Preferred (mirrors Skriptoteket): use the persistent tunnel helper script + LaunchAgent
setup from:
- `docs/operations/hemma-alpha-rollout-days-1-3.md`

```bash
# Start both tunnels (LanguageTool + embeddings)
~/bin/hemma-huleedu-tunnel start

# Check status
~/bin/hemma-huleedu-tunnel status
```

Manual one-off alternative (dedicated terminal tab):

```bash
ssh hemma -L 18085:127.0.0.1:8085
ssh hemma -L 19000:127.0.0.1:9000
```

Local verification:
```bash
curl -fsS http://127.0.0.1:18085/healthz
curl -fsS http://127.0.0.1:19000/healthz
```

### Hemma compose layering (enforce localhost-only services)

On Hemma, layer `docker-compose.hemma.research.yml` on top of the normal compose files.
This binds research/support services (LanguageTool + embedding offload) to `127.0.0.1`
so they are not part of the public surface area.

```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose -f docker-compose.hemma.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml up -d'
```

Note:
- `language_tool_service` is intentionally deployable without Kafka/Redis for research
  (it is stateless and runs a managed Java subprocess).

Enable the embedding offload container (profile-gated):
```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose -f docker-compose.hemma.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml --profile research-offload up -d --build essay_embed_offload'
```

### Restart a specific service

If the service is already deployed via compose on Hemma:
```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose -f docker-compose.hemma.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml up -d --no-deps --force-recreate language_tool_service'
```

Canonical checkout location: `~/apps/huleedu` (mirror Skriptoteket under `~/apps/`).

### Rebuild + restart (when Dockerfile or deps changed)

```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose -f docker-compose.hemma.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml up -d --build language_tool_service'
```

### When Skriptoteket is also impacted

Treat nginx-proxy, shared networks, and port bindings as the shared failure domain.
Verify the reverse proxy container and its upstream configs before debugging app logic.

## Prevention

- Bind Hemma-only services to `127.0.0.1` and expose them to the Mac via tunnels.
- Keep model caches and persistent artifacts on explicit volumes (avoid “container-local”
  caches that vanish on rebuild).
- Prefer deterministic feature extraction outputs and disk caching on the Mac so that
  training/evaluation remains fast even if Hemma is busy.
- Keep this runbook current with the actual Hemma deployment layout (compose file paths,
  container names, ports).
