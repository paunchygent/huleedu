---
id: 'TASK-DEV-DOCKER-LOCK-ALIGNMENT'
title: 'TASK – Align Dev Docker Builds With Single-Lockfile Workflow'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'infrastructure'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-16'
last_updated: '2025-11-17'
related: []
labels: []
---
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

## Context7 Findings (PDM Behavior) – 2025-11-07

Docs pulled via `/pdm-project/pdm` (Context7) reinforce the plan:

- `pdm install` installs every locked dependency group by default; adding `--prod` or `-G` narrows scope, and `--frozen-lockfile` enforces that the lock is respected instead of regenerated. That is exactly what we need for both dev (`--dev --frozen-lockfile`) and prod (`--prod --frozen-lockfile`) layers.
- Editable monorepo dependencies should use `-e file:///${PROJECT_ROOT}/…` in the root `pyproject.toml`. Those paths resolve correctly only when the install runs from the repo root (`${PROJECT_ROOT}=/app` inside containers). Running PDM from `services/<name>` breaks that resolution, which is why every dev Dockerfile currently re-locks.
- `pdm config` lives at the project root and can be altered with `pdm config --local`; in our case we don’t need overrides, but the docs make it explicit that “project root + shared lockfile” is the intended workflow for multi-package repos.

## Recommended Changes (Derived from PDM Docs)

1. **Shared dependency stage** for every Dockerfile:
   - `FROM python:3.11-slim AS deps`
   - Set `WORKDIR /app` and `ENV PROJECT_ROOT=/app PDM_USE_VENV=false PYTHONPATH=/app`
   - Copy `pyproject.toml`, `pdm.lock`, and the `pyproject.toml` + `src/` trees for every library that gets installed via editable `file:///${PROJECT_ROOT}/…`.
   - Run `pdm install --dev --frozen-lockfile` (dev image) and `pdm install --prod --frozen-lockfile` (prod image) from `/app`, leveraging the shared lock.
2. **Service stages** (`development` + `production`) simply `COPY services/<name>/ /app/services/<name>/` and reuse the deps stage—no more per-service `pdm lock`.
3. **docker-compose.dev.yml**: remove all `/app/services/<service>/__pypackages__` named volumes. Rely on the baked dependency layer; keep only source bind mounts for hot reload.
4. **Developer workflow**: emphasize that touching any `pyproject.toml` or `pdm.lock` requires `pdm run dev-build[-clean] <service>` so the shared deps layer is rebuilt (since the lock hash controls that cache layer).
5. **Docs/Rules**: note in `.claude/rules/015` or `040` (and in `HANDOFF.md`) that `pdm` must run from repo root in Docker contexts, referencing the monorepo guidance from the official PDM docs to prevent regressions.

## Implementation Progress

- **NLP Service (2025-11-07)**: Both `services/nlp_service/Dockerfile` and `Dockerfile.dev` now copy the root `pyproject.toml` + `pdm.lock`, include shared-library `pyproject`/`src` trees, and run `pdm install --prod/--dev --frozen-lockfile` from `/app`. `docker-compose.dev.yml` no longer mounts `/app/services/nlp_service/__pypackages__`. Clean BuildKit run via `pdm run dev-build-clean nlp_service` succeeded, `pdm run dev-start nlp_service` confirms hot-reload still propagates code edits, and the functional diagnostic (`pdm run pytest-root services/nlp_service/tests/functional/test_nlp_language_tool_interaction_diagnostic.py`) passes.
- **All remaining services (2025-11-07)**: Added `scripts/update_service_dockerfiles.py` to generate consistent Dockerfile/Dockerfile.dev pairs that (a) share the root dependency install stage, (b) run `pdm install --dev/--prod --frozen-lockfile` from `/app`, and (c) invoke runtime entrypoints via `pdm run -p /app ...`. Regenerated every service Dockerfile except NLP to follow this pattern, preserving service-specific apt dependencies (e.g., `libmagic1`, `openjdk-21-jre-headless`) and default commands. Removed every `/app/services/<service>/__pypackages__` volume mapping from `docker-compose.dev.yml` and updated the `essay_lifecycle_service` worker/API overrides to call `pdm run -p /app python services/essay_lifecycle_service/{app,worker_main}.py`. Remaining work: run representative builds/tests for a subset of services to spot-check the new images, then document the new pattern in `.claude/HANDOFF.md` + rules.

## Next Iteration: Shared Dependency Image

1. **Root-level dep image**: Add `Dockerfile.deps` at repo root that copies `pyproject.toml`, `pdm.lock`, and all shared library `pyproject`/`src` trees, then runs `pdm install --dev --frozen-lockfile` (and optionally `--prod`) from `/app`. Tag the resulting image (e.g., `huledu-deps:<hash>`).
2. **Hash-based invalidation**: Extend the existing `pdm run dev-build[-clean]` flow to compute a hash over all dependency inputs (root `pyproject.toml`, `pdm.lock`, `libs/common_core/**`, `libs/huleedu_service_libs/**`, `libs/huleedu_nlp_shared/**`, etc.). When the hash changes—or when `dev-build-clean` is invoked—rebuild the deps image once and retag it with the new hash before building services.
3. **Service Dockerfiles inherit from deps image**: Regenerate every service Dockerfile so the `FROM` stage uses the shared deps image. Service Dockerfiles will only install additional OS packages (if needed), copy service code, and set `CMD`; no service-specific PDM install stages remain.
4. **Compose wiring**: Ensure `docker-compose.dev.yml` references the deps image tag (e.g., via build args or env var) so service rebuilds automatically pick up updated deps whenever the hash changes.
5. **No `__pypackages__` volumes**: Continue omitting per-service `__pypackages__` mounts—the shared deps image provides all packages.

This restores clean-build performance (heavy install runs once per dependency change) while keeping the single-lockfile workflow and eliminating stale packages.

## Definition of Done

- Dev and prod images for every service install dependencies using the shared lockfile without regenerating it.
- Builds respect the “run `pdm` from repo root” rule.
- Build times improve (no 2–3 minute stalls) and Docker caching is effective.
- Documentation/task checklist updated so future services follow the same template.
