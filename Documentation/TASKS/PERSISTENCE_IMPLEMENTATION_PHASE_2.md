# Task: Persistence Implementation – Phase 2

## Background
Some services still rely solely on in-memory data, object-storage, or transient Redis helpers.  This blocks horizontal scaling, disaster recovery, and full audit capabilities.

| Service | Current State | Gap |
|---------|---------------|-----|
| **spell_checker_service** | Idempotency via Redis only | No durable store for spell-check results & job metadata |
| **cj_assessment_service** | Same as spell-checker | No durable store for assessment results & config |
| **api_gateway_service** | Stateless | Needs persistent session & API analytics (Auth, rate-limit) |
| **file_service** | Persists files to MinIO/S3, but no DB index; Redis pub/sub only | Missing metadata index, versioning, soft-delete tracking |
| **content_service** | Mock in-memory datastore | Requires proper CRUD DB with joins/relations |

## Goals
1. Design and integrate **service-aligned** persistence layers (PostgreSQL preferred; Redis for high-throughput ephemeral data where justified).
2. Follow existing patterns:  async SQLAlchemy, `typing.Protocol` contracts, Dishka DI container, Prometheus metrics.
3. Provide Alembic migrations for schema evolution.
4. Ensure all CRUD operations are covered with integration tests and repository protocols.

## Non-Goals
• Re-architecting business logic beyond what is necessary for persistence integration.
• Creating fallbacks for legacy code paths.

## Deliverables
- Repository protocol + concrete implementation per service (`*_repository_postgres_impl.py` or equivalent).
- `models_db.py` with SQLAlchemy declarative models and enums.
- Alembic revisions committed under each service’s `alembic/` directory.
- Service startup wiring (`di.py` or `startup_setup.py`) registering repositories before use.
- Integration test suite exercising CRUD paths.
- Documentation: update rule 040, 070 with new patterns if novel techniques introduced.

## Acceptance Criteria
1. For each target service, unit + integration tests pass (`pdm run pytest services/<service>/tests -s`).
2. Alembic migrations run cleanly against fresh & existing DBs.
3. Service can start in docker-compose environment with new DB dependency (update `docker-compose.services.yml`).
4. Prometheus metrics include DB query histogram/counter.
5. No lint (ruff+pylint) or type (mypy) violations.
6. Update project README & per-service README with environment variables and migration instructions.

## Implementation Outline
1. **Schema Design** – draft ER models for each service; review with team.
2. **Model + Repository** – code SQLAlchemy models, repository protocols & impls.
3. **DI Wiring** – register repositories via Dishka before blueprint registration.
4. **Migrations** – generate first Alembic revision; commit.
5. **Tests** – write happy-path + failure integration tests with testcontainers-pg.
6. **Docs & Metrics** – update docs, add `db_query_duration_seconds` histogram.

## Timeline (suggested)
| Week | Milestone |
|------|-----------|
| 1 | Complete schemas & repository skeletons |
| 2 | Finish implementations for spell_checker & cj_assessment |
| 3 | Finish api_gateway, file_service, content_service |
| 4 | Tests, metrics, docs, PR review |

---
*Created 2025-06-30 – owner: Platform Engineering*
