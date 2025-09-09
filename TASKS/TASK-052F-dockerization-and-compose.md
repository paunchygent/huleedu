# TASK-052F — Dockerization & Compose

## Objective

Produce a production‑ready container for the Language Tool Service that bundles Python + Java and adheres to repository containerization standards.

## Dockerfile Requirements (Rule 084)

- Base: `python:3.11-slim`; set `PYTHONPATH=/app`, non‑root `appuser`, install PDM.
- Copy `libs/common_core` and `libs/huleedu_service_libs` before service code for caching.
- Install LanguageTool JRE dependency or copy LT artifacts from a builder stage.
- `CMD ["pdm", "run", "start"]` for HTTP mode.

## Compose Integration

- Service: `language_tool_service`
- Port: internal `8085`; mapped externally as needed
- Environment:
  - `ENV_TYPE=docker`
  - `{PREFIX}_HTTP_PORT=8085`
  - Wrapper config: heap size, timeouts

## Health & Validation

- Health check: `curl -f http://localhost:8085/healthz`
- Metrics: `curl -f http://localhost:8085/metrics`
- Compose: `docker compose build --no-cache language_tool_service && docker compose up -d language_tool_service`

## Deliverables

- `Dockerfile` and optional `Dockerfile.dev` with hot‑reload support.
- Compose stanza and docs.

