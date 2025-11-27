# HANDOFF: Current Session Context

## Purpose

This document contains ONLY current/next-session work. All completed tasks, architectural decisions, and patterns are documented in:

- **README_FIRST.md** - Architectural overview, decisions, service status
- **Service READMEs** - Service-specific patterns, error handling, testing
- **.claude/rules/** - Implementation standards and requirements
- **Documentation/OPERATIONS/** - Operational runbooks (see docs/operations/cj-assessment-foundation.md for CJ/LLM defaults & metrics)
- **TASKS/** - Detailed task documentation

---

## 🎯 ACTIVE WORK (2025-11-27)

### Filename Propagation Gap (NEW - high priority)
**Root Cause Identified**: `EssaySlotAssignedV1` event missing `original_file_name` field.
- File Service → ELS: filename included ✅
- ELS → RAS: filename **MISSING** in event ❌
- Result: `essay_results.filename` is NULL, teachers can't identify students

**Impact**:
- GUEST batches: **Critical** - filename is ONLY way to identify students (no class_id)
- REGULAR batches: filename needed until student matching completes

**Task Created**: `TASKS/assessment/filename-propagation-from-els-to-ras-for-teacher-result-visibility.md`
- 6 files to modify (event contract + ELS publisher + RAS handler/protocol/repo/updater)
- No DB migrations needed (column exists)
- ~2-3 hours implementation

**Investigation Report**: `.claude/work/reports/2025-11-27-filename-propagation-flow-mapping.md`

### LLM Provider Configuration Hierarchy (COMPLETED)
- Documented 3-tier override hierarchy: `USE_MOCK_LLM` (absolute) → request `provider_override` → service defaults
- Created runbook: `docs/operations/llm-provider-configuration-hierarchy.md`
- Added rule section: `.claude/rules/020.13-llm-provider-service-architecture.md` § 6.2.1
- Key insight: request-level overrides CANNOT bypass `USE_MOCK_LLM=true` (DI boot-time decision)

### JWT Secret Fix (COMPLETED)
- **Bug**: `docker-compose.dev.yml:177` had hardcoded `JWT_SECRET_KEY=test-secret-key`
- **Symptom**: Functional tests got 401 Unauthorized (signature mismatch)
- **Fix**: Changed to `JWT_SECRET_KEY=${JWT_SECRET_KEY}` to use `.env` value
- CJ functional test now passes: `test_complete_cj_assessment_processing_pipeline`

### CJ Runbook User Stories (COMPLETED)
- Added User Stories section to `docs/operations/cj-assessment-foundation.md`
- US-1: Teacher views CJ results with student identification
- US-2: GUEST batch assessment (no class association)
- US-3: REGULAR batch assessment (class association)
- US-4: Optional spellcheck (future)
- Added data flow requirements table

### Ingestion traceability + mock LLM guard (completed earlier today)
- Migration `20251127_1200` applied: `assignment_id` column + indexes on `text_storage_id`
- File uploads now store `assignment_id` for CJ traceability
- Functional harness enforces mock LLM
- All targeted unit tests passing

### Functional Test Harness Ergonomics (carry-over)
- Readiness gate, Kafka topic precreation, Redis cleanup, timeout markers, and dev-stack-only guidance already in place (see notes from 2025-11-26).
- Functional CJ tests should still wait until assignment_id + ENG5 bundle alignment is verified (see pending above).

### Deprecate CJ registration flag at batch registration (started)
- Step 1 done: marked field deprecated in `BatchRegistrationRequestV1` (code + docs) and added AGW warning log when the flag is set.
- Step 2 done: BOS now ignores the flag entirely for pipeline selection (registration metrics record registration only), and pipeline-request flow drives pipeline state; regression tests added to ensure CJ inclusion/exclusion depends solely on `ClientBatchPipelineRequestV1`.
- Step 3 done (local codebase): field fully removed from contracts, AGW/BOS code, and tests; only pipeline-request–driven selection remains. No runtime monitoring available in non-deployed env.
- Doc cleanup: Removed remaining references to the deprecated flag from TASKS docs; repository search is now clean.

---

## ➡️ Forward to next agent

### Priority 1: Filename Propagation Fix (HIGH)
Implement task: `TASKS/assessment/filename-propagation-from-els-to-ras-for-teacher-result-visibility.md`
1. Add `original_file_name: str` to `EssaySlotAssignedV1` event contract
2. Update ELS to include filename when publishing slot assignment
3. Update RAS to consume filename and populate `essay_results.filename`
4. Add tests (unit + E2E for GUEST batch filename visibility)

### Priority 2: Verify CJ Functional Test Suite
- CJ functional test now passes with JWT fix
- Verify filename appears in RAS results after propagation fix
- Align functional essay bundle with ENG5 runner student set

### Priority 3: Staged Submission for CJ
- Implement wave-based submission with stability checks (non-batch-API modes)
- Settings wiring and tests (see CJ runbook § Planned PR)

---

## ✅ CJ/LPS Boundary Validation Coverage (2025-11-26)

### Validated with Real Services (HTTP + Kafka)

| Test File | What's Validated | Evidence |
|-----------|------------------|----------|
| `test_cj_lps_metadata_roundtrip.py` | Real HTTP POST to LPS, Kafka callback, metadata preservation | Uses `aiohttp.ClientSession()`, `@pytest.mark.docker` |
| `test_cj_lps_manifest_contract.py` | Model discovery `/api/v1/models`, LLMConfigOverrides | Uses real HTTP calls |

### Validated with Unit Tests (Mocked Dependencies)

| Test File | What's Validated |
|-----------|------------------|
| `test_llm_callback_processing.py` | LLMComparisonResultV1 parsing, winner determination |
| `test_callback_state_manager.py` | Correlation ID matching, state restoration |
| `test_llm_provider_service_client.py` | HTTP request construction, 202 response handling |
| `test_callback_publishing.py` | EventEnvelope construction, confidence scale (0-1→1-5) |
| `test_health_routes.py` (NEW) | /healthz, /metrics endpoints, provider status |
| `test_comparison_routes.py` (NEW) | /comparison POST, error handling, correlation ID |

### NOT YET Validated
- Rate limiting behavior under load
- Circuit breaker state transitions under real failures
- Kafka consumer reconnection after broker failure
- LPS queue overflow scenarios

---

## ✅ RECENTLY COMPLETED (Reference Only)

- **2025-11-26 LLM Provider Service Error Handling Bug FIXED** - Double-jsonify bug in `llm_routes.py:137` resolved:
  - Created `error_handlers.py` with LPS-specific handler using `create_error_response` factory
  - Registered handler in `startup_setup.py`
  - Added model to all provider error details (anthropic, openrouter, mock) for metrics
  - Fixed `llm_routes.py` exception handling: added `except HuleEduError: raise` before generic `except Exception` to allow propagation to app-level handler
  - Created `test_error_handler_pattern.py` (5 tests) validating provider/model preservation and no double-jsonify
  - 411 tests passing, typecheck clean (1333 files)
  - Report: `.claude/work/reports/2025-11-26-llm-provider-error-handling-bug.md`

- **2025-11-26 CJ/LPS Boundary Validation COMPLETE** - All boundary tests passing:
  - Step 1: Docker infrastructure verified
  - Step 2: CJ/LPS unit tests - **72 passed**
  - Step 3: Cross-service contract tests - **22 passed**
  - Step 4: CJ↔LPS boundary tests - **7 passed**
  - Step 5: Full pipeline boundary tests - **10 passed**
  - Step 6: Created `test_health_routes.py` - **6 tests**
  - Step 7: Created `test_comparison_routes.py` - **8 tests**
  - Step 8: Format/lint passed
  - Step 9: typecheck-all passed (1331 files, 0 errors)
- **2025-11-26 CJ Repository Refactoring COMPLETE** - 690 tests passing. CJRepositoryProtocol removed, per-aggregate repository pattern enforced.
- **2025-11-26 Port/Metrics Standardization** - All services expose `/metrics` on HTTP port.
- **2025-11-25 CJ Assessment Test Debugging** - Fixed 22 test failures (29→7).
- **2025-11-24 CJ Repository Refactoring Waves 1-4** - 60+ files modified, all quality gates passing.
