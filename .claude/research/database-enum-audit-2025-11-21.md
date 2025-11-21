# Database Enum Audit – 2025-11-21

## Git history timeline (BatchStatus & EssayStatus)
- 2025-07-06: Initial Alembic migrations created with minimal enums  
  - `essay_status_enum` = 10 values (`services/essay_lifecycle_service/alembic/versions/20250706_0001_initial_schema.py`).  
  - `batch_status_enum` = 5 values (`services/batch_orchestrator_service/alembic/versions/20250706_0001_initial_schema.py`).  
- 2025-07-17: Refactor commit adds **full status_enums.py** (31 EssayStatus, 12 BatchStatus) with no accompanying migrations (commit `809af2d1`).  
- 2025-08-02: BatchStatus refactor (removes `guest_class_ready`) still no migration update (commit `20be390a`).  
- 2025-08-05: Adds `STUDENT_VALIDATION_COMPLETED` to BatchStatus without migration (commit `a938fd0c`).  
- 2025-11-11: Doc-only update to status_enums (commit `c1774377`) – values unchanged.  

**Conclusion:** Divergence began July 17, 2025 when enumerations were bulk-added to Python without matching migrations (Hypothesis 1: one-time bulk addition). Initial schemas were intentionally minimal, and no guardrails caught the drift, allowing it to persist until 2025-11-21.

## Service-by-service audit

| Service | Python Enum | DB Enum | Python Values | DB Values | Mismatch? | Critical? |
|---------|-------------|---------|---------------|-----------|-----------|-----------|
| Essay Lifecycle (ELS) | `EssayStatus` (common_core) | `essay_status_enum` | 31 | 41 | Fixed (DB superset after 2025-11-21 migrations) | YES |
| Batch Orchestrator (BOS) | `BatchStatus` (common_core) | `batch_status_enum` | 12 | 15 | Fixed (DB superset after 2025-11-21 migration) | YES |
| CJ Assessment | `CJBatchStatusEnum` (service) | `cj_batch_status_enum` | 8 | 8 | No | HIGH |
| Result Aggregator | `BatchStatus` (common_core) | `batchstatus` | 12 | 12 | No | HIGH |
| Spellchecker | Uses `EssayStatus` only (no service enums) | — (no enums) | 31 | — | No | MED |
| File Service | — | — | — | — | No enums | MED |
| Class Management | Course/language enums only (no status machine) | `course_code_enum`, `language_enum` | n/a | match | No | MED |
| NLP Service | `MatchStatus` (3) | — (no enums) | 3 | — | No enums | LOW |
| Email Service | `EmailStatus` (6) | `email_status_enum` | 6 | 6 | No | LOW |
| Entitlements | `OperationStatus` (3) | `operation_status_enum` | 3 | 3 | No | LOW |

## Root cause
- Single bulk introduction of expanded enums on 2025-07-17 without migrations, followed by later additions (2025-08-05) still missing migrations.  
- Initial migrations intentionally minimal (Hypothesis 3 flavor) but not followed by catch-up migrations, and no CI/pre-commit validation to detect enum drift (process gap).  

## Prevention recommendations
- Add a CI/pre-commit check that compares Python enum members in `common_core.status_enums` (and service-local enums) against database enum definitions generated from latest Alembic revisions; fail if drift detected.  
- Require migrations whenever `Enum` classes change (Rule 085 update).  
- Optional runtime guard: startup check that queries `pg_type` for enums referenced by SQLAlchemy `Enum` columns and raises on mismatch in non-prod to fail fast.

## Outstanding work
- No additional mismatches found across audited services (9/9 checked).  
- Maintain watch: future enum edits must ship with migrations and updated CI check once added.  

## Prevention implemented (2025-11-21)
- Added `pdm run validate-enum-drift` to fail when Python enums are missing in DB enums (dev DBs required).  
- Added startup fail-fast enum validation in BOS and ELS for non-production environments.  
- Aligned `CONTENT_INGESTING` value in `EssayStatus` with DB (`content_ingesting`); legacy typo removed, validator now fully clean.  
