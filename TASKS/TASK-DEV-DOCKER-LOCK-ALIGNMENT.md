# TASK – Align Dev Docker Builds With Single-Lockfile Workflow

**Created:** 2025-11-07  
**Owner:** Platform Eng (Dev Tooling)  
**Status:** New / Needs Scoping

## Problem Statement

The development Dockerfiles (verified on `services/nlp_service/Dockerfile.dev`) re-run `pdm lock` inside each service subdirectory during the `base` stage. Because the HuleEdu repo enforces a **single lockfile at the root**, this pattern:

- Violates the rule "`pdm` commands must run from repo root with the shared lockfile".
- Forces every dev build (`pdm run dev-build[-clean] <service>`) to recompute dependency resolution, adding 2–3 minutes to step `base 10/14`.
- Prevents Docker layer caching of dependencies even when nothing changed, increasing iteration time for all containerized services.

## Immediate Impact

`pdm run dev-build-clean nlp_service` consistently stalls during:

```
Step 10/14 : WORKDIR /app/services/nlp_service
Step 11/14 : RUN pdm lock --lockfile pdm.lock.docker ...
```

The lock generation hits the network and resolves the entire dependency tree before the build can proceed, even for minor code edits.

## Proposed Solution

1. **Adopt the root lockfile in dev images.**
   - Copy `/pyproject.toml` and `/pdm.lock` into `/app/`.
   - Run `pdm install --dev --frozen-lockfile` from `/app` (repo root).
   - Remove the per-service `pdm lock` calls and any temporary lockfiles.

2. **Extend the audit to every service Dockerfile (.dev and prod).**
   - Identify which images still install dependencies from a subdirectory or regenerate locks.
   - Where feasible, switch them to the same root-lock install flow so we maintain a single source of truth and gain caching benefits everywhere.

3. **Document the pattern** in `.claude/rules` (probably 015 or 040) so future Dockerfiles inherit it automatically.

## Research To Do

- [ ] Inventory all `services/*/Dockerfile` and `Dockerfile.dev` files for `pdm lock` / `pip install` patterns.
- [ ] Note which services already consume the root lock (e.g., production Dockerfiles doing `COPY pdm.lock ...`).
- [ ] Prototype the root-lock install flow for `nlp_service` dev Dockerfile and measure build-time delta.
- [ ] Roll out the change to other services (batch orchestrator, ELS API/worker, CJ, etc.).

## Audit – 2025-11-07

**Summary**

- Every dev Dockerfile copies only the service-level `pyproject.toml`, runs `WORKDIR /app/services/<service>` and executes `pdm lock --lockfile pdm.lock.docker` followed by `pdm install --dev` from that subdirectory. This breaks the "run pdm from repo root" rule and guarantees a re-lock for every dev build.
- Every prod Dockerfile copies the shared `pdm.lock` *into* the service folder and executes `pdm install --prod --frozen-lockfile` from `/app/services/<service>`. While the frozen lock prevents re-resolution, it is still invoked outside the repo root so it cannot reuse the dependency layer between services.
- `docker-compose.dev.yml` mounts anonymous volumes at `/app/services/<service>/__pypackages__` for all services, so interpreter bytecode and PDM-installed wheels survive `docker compose down -v` unless those named volumes are explicitly pruned. This is the mechanism that kept stale packages alive for the NLP container.

| Service | Dev re-locks? | Dev install scope | Prod install scope | Prod copies root lock? | Notes |
|---|---|---|---|---|---|
| api_gateway_service | yes | service dir | service dir | yes | `services/api_gateway_service/Dockerfile(.dev)` |
| batch_conductor_service | yes | service dir | service dir | yes | `services/batch_conductor_service/Dockerfile(.dev)` |
| batch_orchestrator_service | yes | service dir | service dir | yes | `services/batch_orchestrator_service/Dockerfile(.dev)` |
| cj_assessment_service | yes | service dir | service dir | yes | `services/cj_assessment_service/Dockerfile(.dev)` |
| class_management_service | yes | service dir | service dir | yes | `services/class_management_service/Dockerfile(.dev)` |
| content_service | yes | service dir | service dir | yes | `services/content_service/Dockerfile(.dev)` |
| email_service | yes | service dir | service dir | yes | `services/email_service/Dockerfile(.dev)` |
| entitlements_service | yes | service dir | service dir | yes | `services/entitlements_service/Dockerfile(.dev)` |
| essay_lifecycle_service | yes | service dir | service dir | yes | `services/essay_lifecycle_service/Dockerfile(.dev)` |
| file_service | yes | service dir | service dir | yes | `services/file_service/Dockerfile(.dev)` |
| identity_service | yes | service dir | service dir | yes | `services/identity_service/Dockerfile(.dev)` |
| language_tool_service | yes | service dir | service dir | yes | `services/language_tool_service/Dockerfile(.dev)` |
| llm_provider_service | yes | service dir | service dir | yes | `services/llm_provider_service/Dockerfile(.dev)` |
| nlp_service | yes | service dir | service dir | yes | `services/nlp_service/Dockerfile(.dev)` |
| result_aggregator_service | yes | service dir | service dir | yes | `services/result_aggregator_service/Dockerfile(.dev)` |
| spellchecker_service | yes | service dir | service dir | yes | `services/spellchecker_service/Dockerfile(.dev)` |
| websocket_service | yes | service dir | service dir | yes | `services/websocket_service/Dockerfile(.dev)` |

> All dev/prod Dockerfiles are therefore high-risk for dependency drift: any service rebuild can mutate its own `__pypackages__`, and nothing consumes the canonical root install plan.

## Design – Root-Level PDM Install Pattern

**Goals**

1. Run every dependency install from `/app` (repo root) with `pdm install --frozen-lockfile`.
2. Bake the dependency layer into the image so hot-reload containers stop mounting `__pypackages__`.
3. Keep editable `-e file:///${PROJECT_ROOT}/...` links functional so shared libs and services still resolve inside containers.

**Planned Pattern**

```
FROM python:3.11-slim AS deps-base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PDM_USE_VENV=false PROJECT_ROOT=/app PYTHONPATH=/app
RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential python3-dev \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pdm
WORKDIR /app
# Copy only metadata + shared lib sources to maximize caching
COPY pyproject.toml pdm.lock ./
COPY libs/common_core/pyproject.toml libs/common_core/pyproject.toml
COPY libs/common_core/src/ libs/common_core/src/
... (repeat for other libs)
COPY services/*/pyproject.toml services/<name>/pyproject.toml

FROM deps-base AS deps-dev
RUN --mount=type=cache,target=/root/.cache/pip pdm install --dev --frozen-lockfile

FROM deps-base AS deps-prod
RUN --mount=type=cache,target=/root/.cache/pip pdm install --prod --frozen-lockfile

FROM deps-dev AS development
COPY services/<service>/ /app/services/<service>/
...

FROM deps-prod AS production
COPY services/<service>/ /app/services/<service>/
...
```

**Compose / Volume Strategy**

- Remove the anonymous `__pypackages__` volumes from `docker-compose.dev.yml`. The baked dependency layer in the dev image will supply packages, so bind-mounting `__pypackages__` is no longer necessary (and is the root cause of stale wheels).
- Keep the code bind mounts (`./services/<service>:/app/services/<service>`) so hot reload works, but rely on rebuilds to pick up dependency changes.
- Document that developers must run `pdm run dev-build <service>` after touching `pyproject.toml` or `pdm.lock`.

**Editable Dependencies**

- Root `pyproject.toml` already pins every library and service via `-e file:///${PROJECT_ROOT}/...`. Copying each service’s `pyproject.toml` into the dependency layer ensures the editable paths exist; copying shared library `src/` directories allows `pdm install` to lay down `.pth` links.
- For services that need extra shared packages (e.g., `huleedu_nlp_shared`), we copy their `src/` trees once in the deps stage so both dev and prod builds reuse the same cached artifact.

**Result**

- `pdm install` only runs twice per Dockerfile (once for dev, once for prod) and always uses the shared lock.
- Dev containers no longer persist `__pypackages__` between rebuilds; deleting/stopping a container is sufficient to guarantee a clean environment.
- All services share the exact same dependency image slice, so docker layer caching remains effective even when building different services back-to-back.

## Definition of Done

- Dev and prod images for every service install dependencies using the shared lockfile without regenerating it.
- Builds respect the “run `pdm` from repo root” rule.
- Build times improve (no 2–3 minute stalls) and Docker caching is effective.
- Documentation/task checklist updated so future services follow the same template.
