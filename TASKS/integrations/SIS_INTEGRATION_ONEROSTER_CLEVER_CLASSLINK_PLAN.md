---
id: 'SIS_INTEGRATION_ONEROSTER_CLEVER_CLASSLINK_PLAN'
title: 'SIS Integration Plan: OneRoster + Clever + ClassLink (Weeks 2–6)'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'integrations'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-08-23'
last_updated: '2025-11-17'
related: []
labels: []
---
# SIS Integration Plan: OneRoster + Clever + ClassLink (Weeks 2–6)

Objective
- Ingest rosters from SIS/LMS via OneRoster (CSV/REST) and connectors (Clever/ClassLink) into CMS.

Scope
- In: CSV import pipeline, REST OneRoster client, connector auth flows (tokens), scheduled sync + delta updates.
- Out: Full district admin portal (future), advanced de-duplication heuristics (phase 2).

References
- CMS: `services/class_management_service/*` (API, models, DI)
- NLP Phase 1: matching relies on accurate rosters
- Rules: `020`, `042`, `053-sqlalchemy-standards`, `070`

Deliverables
1. CSV Import: CLI + API to import OneRoster CSV to CMS.
2. REST Import: OneRoster REST client with pagination and filtering.
3. Connectors: Clever/ClassLink token exchange and fetch.
4. Scheduler: Periodic sync job; delta detection; basic idempotency.
5. Tests: Integration tests with fixtures; idempotent re-runs.

Work Packages
1) Data Model & Migrations (CMS)
   - Extend CMS schemas for external IDs (sourcedId, vendor ids) and sync state tables.
   - Alembic migrations, repository methods, indexes.
   - Acceptance: External IDs persisted; unique constraints enforced.

2) Importers
   - CSV: `cms/api/internal_routes.py` new endpoints for upload + background import worker.
   - REST: `libs` or `services` client for OneRoster REST; map to CMS DTOs.
   - Acceptance: CSV + REST import produce identical entity graphs on sample data.

3) Connectors
   - Clever/ClassLink: OAuth/token config; fetch classes, users, enrollments.
   - Acceptance: Successful fetch, transform, and upsert into CMS.

4) Scheduling & Delta
   - Add periodic task (worker) to refresh data and detect deltas based on updatedAt.
   - Acceptance: Re-run safe; no duplicates; metrics expose counts.

5) Tests + Docs
   - E2E tests in `services/class_management_service/tests/` with sample OneRoster data.
   - Docs: Import instructions, mapping decisions, failure modes.

Dependencies
- SIS/API tokens; OneRoster sample datasets.

Risks/Mitigations
- Data quality variance ➜ robust validation and dead-letter report for rejects.

Definition of Done
- OneRoster CSV/REST import usable; Clever/ClassLink fetch + upsert working; periodic sync in place; tests pass.
