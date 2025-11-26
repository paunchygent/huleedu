# Review: Docker Port Configuration Standardization Plan  
**Date:** 2025-11-26  
**Reviewer:** Codex (GPT-5)  
**Scope:** Plan-only review (no code diff provided) for port/metrics standardization across services, Docker Compose, Prometheus, and new governance artifacts.

---

## Verdict
Needs design changes before implementation. The plan collides with current runtime behavior (metrics exposure model, Dockerfile bindings, rule numbering) and would break observability for several services without additional code changes.

---

## Key Findings (ordered by impact)
- **Metrics exposure model is inconsistent today and the plan widens the gap.**  
  - `result_aggregator_service` already runs a **separate metrics server** via `prometheus_client.start_http_server` on `METRICS_PORT` (9096) and does *not* expose `/metrics` on its HTTP port; Prometheus currently scrapes `4003/metrics`, so metrics are already dark for RAS (see `startup_setup.py:32-44`, `docker-compose.services.yml:76-110`, `observability/prometheus/prometheus.yml:62-66`).  
  - Identity/email/file/NLP/ELS expose metrics (where present) on the main HTTP port or not at all (e.g., Identity uses `/metrics` on 7005: `api/health_routes.py:79-89`). Moving Prometheus to scrape new 911x ports will 404 unless each service starts a dedicated metrics server on that port.  
  - NLP currently has no HTTP surface and no metrics server at all; assigning `PROMETHEUS_PORT=9116` without adding a metrics server yields no data.
- **Dockerfiles hard-bind HTTP ports, ignoring config renames.**  
  Hypercorn commands in Dockerfiles lock ports (`identity_service/Dockerfile:19` binds 7005; `email_service/Dockerfile:19` binds 8080). Renaming `PORT→HTTP_PORT` in config/Compose will not change the actual bind address unless the Dockerfile entrypoints are re-plumbed to read the env vars. Risk: config/Compose say one thing while containers still bind the old literals.
- **Rule ID collision.**  
  The plan proposes `.claude/rules/046-docker-port-configuration.md`, but `046` is already `docker-container-debugging.md`. Creating another `046` breaks the rule index and tooling that depends on unique IDs.
- **Validator scope too narrow.**  
  Proposed `scripts/validate_port_config.py` only covers `config.py`, `docker-compose.services.yml`, and `prometheus.yml`. It would miss drift in Dockerfiles (hard-coded binds), alternate compose files (`services/.../tests/distributed/docker-compose.distributed-test.yml`), and service entrypoints that start metrics servers (`result_aggregator_service/startup_setup.py`). Drift would persist despite the hook.
- **Env prefix inconsistency remains.**  
  The plan fixes RAS by adding `env_prefix`, but email keeps `env_prefix="EMAIL_"` while Compose uses `EMAIL_SERVICE_*` for DB vars and `EMAIL_HTTP_PORT`/`EMAIL_PROMETHEUS_PORT`. Decide whether the standard is `{SERVICE}_` or `{SERVICE}_SERVICE_` and align config prefixes; otherwise the validator will green-light configs that still ignore provided env vars.
- **Prometheus job churn & dashboards.**  
  Switching to dedicated 911x jobs will require updating Grafana dashboards/alerts and any SLO burn-rate queries. No migration/compatibility story is included (e.g., dual-scrape window).
- **Host exposure toggle is Compose-only.**  
  `${EXPOSE_METRICS_TO_HOST:+...}` removes host ports but services will still listen on the metrics port. If the security goal includes not binding on the container at all when disabled, an app-level toggle (or `start_http_server` guard) is needed.

---

## Suggestions & Path Forward
1. **Choose a single metrics exposure pattern first.**  
   - Option A (simpler): Keep metrics on the main HTTP port for all services, remove dedicated metrics ports, and fix RAS to serve `/metrics` on its HTTP port instead of a side server.  
   - Option B (more secure/consistent): Standardize on a dedicated Prometheus port per service. Add a small helper in `huleedu_service_libs` to start `start_http_server(settings.PROMETHEUS_PORT)` so every service can opt-in uniformly (workers included). Then move Prometheus jobs to 911x. Document the chosen pattern.
2. **Plumb ports through Dockerfiles.**  
   Replace hard-coded Hypercorn binds with env-driven values (e.g., `--bind 0.0.0.0:${IDENTITY_SERVICE_HTTP_PORT:-7005}`) so config/Compose/Dockerfile stay in sync with the validator.
3. **Fix current observability regression immediately.**  
   Update Prometheus to scrape RAS on its actual metrics port (9096 or the new 9111) and add a temporary dual-scrape if you transition to the new range to avoid data gaps.
4. **Avoid rule ID conflict.**  
   Pick a new rule number (e.g., `084.2-docker-port-configuration.md`) and register it in `000-rule-index.md`.
5. **Broaden the validator.**  
   - Scan Dockerfiles for `--bind` literals.  
   - Scan all compose files (including test/distributed) and service entrypoints that start metrics servers.  
   - Assert that `env_prefix` + field names map to the env vars defined in Compose/.env.  
   - Verify that every service with `PROMETHEUS_PORT` either exposes `/metrics` on that port or has a metrics server registered.
6. **Plan a migration window.**  
   Ship aliases (`HTTP_PORT` with deprecated `PORT` fallback) and dual Prometheus targets for one release to avoid breaking running environments and dashboards.
7. **Document + .env sync.**  
   Add `EXPOSE_METRICS_TO_HOST` to `.env`/`env.example`, clarify reserved ranges (HTTP 4000–8999, Prom 9110–9119), and describe how worker-only services (NLP, ELS workers) should expose metrics.

---

## Open Questions for the Author
1. Do we want dedicated metrics ports for *all* services, including worker-only processes, or only for RAS where a sidecar server already exists?  
2. Should email/identity continue to serve metrics on the HTTP port, or are we adding a side `start_http_server` to match the new 911x plan?  
3. Which env prefix is canonical (`<SERVICE>_` vs `<SERVICE>_SERVICE_`)? The validator and docs should enforce a single choice.  
4. Are we prepared to update Grafana/alerting alongside the Prometheus job changes? If not, can we keep dual targets during the transition?
