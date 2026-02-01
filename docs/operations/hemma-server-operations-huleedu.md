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

### SSH + host reachability

```bash
ssh hemma 'uptime'
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
ssh hemma 'sudo docker logs --tail=200 -f huledu_language_tool_service'
```

Embedding offload server logs (if deployed via `docker run`):
```bash
ssh hemma 'sudo docker logs --tail=200 -f huleedu_essay_embed_offload'
```

## Resolution

### SSH port-forward tunnels (default)

Run these from the Mac (keep them in a dedicated terminal tab):

```bash
# HuleEdu LanguageTool service HTTP API (NOT the Java port)
ssh hemma -L 18085:127.0.0.1:8085

# DeBERTa + spaCy feature offload service
ssh hemma -L 19000:127.0.0.1:9000
```

Local verification:
```bash
curl -fsS http://127.0.0.1:18085/healthz
curl -fsS http://127.0.0.1:19000/healthz
```

### Restart a specific service

If the service is already deployed via compose on Hemma:
```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose up -d --no-deps --force-recreate language_tool_service'
```

Canonical checkout location: `~/apps/huleedu` (mirror Skriptoteket under `~/apps/`).

### Rebuild + restart (when Dockerfile or deps changed)

```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose up -d --build language_tool_service'
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
