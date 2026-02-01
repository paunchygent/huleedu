---
id: multi-tenancy-implementation-plan
title: Multi‑Tenancy Implementation (Weeks 5–8)
type: task
status: proposed
priority: medium
domain: assessment
service: ''
owner_team: agents
owner: ''
program: ''
created: '2025-08-23'
last_updated: '2026-02-01'
related: []
labels: []
---
Objective

- Introduce tenant isolation across data, events, and rate limits to support schools/districts.

Scope

- In: `tenant_id` propagation, DB schema updates, cache separation, per‑tenant rate limits/quotas, LLM usage tracking.
- Out: Full billing integration (tracked separately).

References

- Services DB layers: `services/*/models_db.py`, Alembic per service
- Gateway: `services/api_gateway_service/app/rate_limiter.py`
- Events: `libs/common_core/src/common_core/events/*`, `event_enums.py`, `envelope.py`
- Rules: `020`, `053`, `070`, `085`

Deliverables

1. Tenant ID in JWT and gateway headers (from Identity/SSO claims).
2. DB: Add `tenant_id` columns + indexes where applicable; update repositories.
3. Cache: Redis key namespaces include tenant.
4. Rate limits/quotas: Per‑tenant limits in gateway; per‑tenant LLM usage counters.
5. Tests: E2E verifying isolation and limits.

Work Packages

1) Contract & Claims
   - Identity issues `tenant_id` claim; gateway forwards header `X-Tenant-ID`.
   - Acceptance: Services log and trust tenant context.

2) DB Migrations (per service)
   - Add `tenant_id` to core tables (batches, essays, users, results). Alembic migrations.
   - Acceptance: Queries filtered by tenant; indexes measured; tests green.

3) Cache Namespacing
   - Update Redis keys to prefix with `tenant:{tenant_id}:...` in repositories and state managers.
   - Acceptance: No cross-tenant cache bleed in tests.

4) Rate Limiting & Quotas
   - Update gateway limiter to apply per-tenant; expose metrics per tenant.
   - LLM Provider: track usage per tenant; expose metrics and soft quotas.
   - Acceptance: Limits enforced; metrics visible in Prometheus.

5) Tests + Docs
   - Add multi-tenant test fixtures; E2E tests across gateway ➜ services.
   - Docs: tenant model, migration guidance, operational notes.

Definition of Done

- Tenant-aware auth, data, cache, and limits in place; tests pass; operational docs updated.
