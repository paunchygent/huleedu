# TASK-048 — Alembic Migration Issues during Monorepo Outbox Verification

## Summary

When running the monorepo outbox index verification (`pdm run db-verify-outbox-all`), several services fail to apply Alembic migrations against a fresh disposable Postgres. This blocks cross-service verification of outbox index alignment.

This task tracks investigation and remediation for the migration issues outside the Entitlements scope.

## Affected Services

- class_management_service
  - Error: “Multiple head revisions are present for given argument 'head' …”
  - Impact: `alembic upgrade head` fails on a fresh DB.

- essay_lifecycle_service
  - Error: DuplicateObjectError: type "essay_status_enum" already exists (from initial migration).
  - Impact: `alembic upgrade head` fails on a fresh DB due to enum type creation.

Entitlements service migrations and outbox verification are green and are not part of this task.

## Why This Matters

- We use a disposable Postgres per service to ensure migrations are reproducible and consistent (Rule 085).
- Migration failures prevent `db-verify-outbox-all` from completing, which is our fast guardrail to keep outbox schemas aligned across services.

## Reproduction

From repository root:

```
# Verify all curated services (slow):
pdm run db-verify-outbox-all

# Verify specific services (faster):
pdm run python scripts/verify_outbox_all_services.py --only class_management_service essay_lifecycle_service --fail-fast
```

Observed failures (examples):

- class_management_service
  - “Multiple head revisions are present for given argument 'head' …”

- essay_lifecycle_service
  - asyncpg.exceptions.DuplicateObjectError: type "essay_status_enum" already exists

## Expected vs Actual

- Expected: On a fresh DB, `alembic upgrade head` (or `heads` where applicable) completes without errors; outbox index verifier prints OK; process exits 0.
- Actual: Migration failures as above; verification aborts for those services.

## Proposed Remediation

Follow Rule 085 (Database Migration Standards) and align service migrations accordingly.

1) class_management_service — Multiple Alembic heads
   - Inspect heads: `pdm run alembic heads` (from the service directory)
   - Merge divergent heads into a single linear head using `alembic merge`.
   - Ensure migrations produce the same schema as currently deployed; avoid destructive changes.
   - Update any CI scripts/documentation to prevent future divergent heads.

2) essay_lifecycle_service — ENUM type duplication
   - Fix the initial migration to define the enum once using SQLAlchemy’s `sa.Enum(..., name='essay_status_enum')` with proper values.
   - Avoid issuing raw `CREATE TYPE` without guards; if raw SQL is necessary, use `IF NOT EXISTS` and ensure column definitions reference the named type.
   - Validate downgrade path: drop dependent columns/tables before dropping the type; ensure safe sequencing.

3) Validation
   - Fresh DB run: `pdm run python scripts/verify_outbox_all_services.py --only class_management_service essay_lifecycle_service`
   - Confirm: migrations apply cleanly; outbox verifier prints `OK: Outbox indexes aligned with shared conventions.` for each service.

## Acceptance Criteria

- class_management_service:
  - A single Alembic head; `alembic upgrade head` works on a fresh DB.
  - `db-verify-outbox-all --only class_management_service` exits 0 and prints OK.

- essay_lifecycle_service:
  - No DuplicateObjectError for `essay_status_enum` on a fresh DB.
  - `db-verify-outbox-all --only essay_lifecycle_service` exits 0 and prints OK.

- Documentation:
  - Brief note added in each service’s README or migrations README on preventing multiple heads and enum creation patterns (Rule 085 references).

## Out of Scope

- Entitlements service functionality, tests, and migrations (already green).
- Changes to shared outbox library or index names.

## References

- Rules:
  - `.cursor/rules/085-database-migration-standards.mdc`
  - `.cursor/rules/042.1-transactional-outbox-patterns.mdc` (outbox context)
  - `.cursor/rules/090-documentation-standards.mdc`

- Scripts and locations:
  - `scripts/verify_outbox_all_services.py`
  - `services/class_management_service/alembic/`
  - `services/essay_lifecycle_service/alembic/versions/20250706_0001_initial_schema.py`

## Notes

- The verifier script was augmented to:
  - Print progress logs immediately, add timeouts, and fall back to `alembic upgrade heads` when multiple heads are detected.
  - These enhancements surface the underlying migration issues but do not fix them; remediation must occur within each service’s migration history.

