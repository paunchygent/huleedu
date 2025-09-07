Entitlements Service
====================

Purpose

- Central authority for credit policies and accounting with org-first identity attribution. Provides advisory preflight and post-usage consumption.

Key Notes

- Outbox schema ownership: This service uses the shared Transactional Outbox model from `libs/huleedu_service_libs.outbox.models.EventOutbox`. Do not define or modify a service-local outbox model. All migrations for the outbox table must align with the shared library conventions (index names, columns, partial index on `published_at IS NULL`).
- Migrations: Create Alembic migrations from this service directory. Avoid modifying pushed versions. Use `.cursor/rules/085-database-migration-standards.mdc` for guidance.

Outbox Index Alignment

- Shared index names used by the library:
  - `ix_event_outbox_unpublished` on (`published_at`, `created_at`) with predicate `published_at IS NULL`.
  - `ix_event_outbox_aggregate` on (`aggregate_type`, `aggregate_id`).
- A migration is provided to align legacy aliases to these names: `alembic/versions/20250907_1415_align_outbox_index_names.py`.

Verification

- Alembic chain check (from `services/entitlements_service/`):
  - `pdm run alembic heads`
  - `pdm run alembic history --verbose`
- Index verification script:
  - `python services/entitlements_service/scripts/verify_outbox_indexes.py --database-url postgresql+asyncpg://user:pass@host:port/db`
  - Returns non-zero exit code on missing/mismatched indexes.
