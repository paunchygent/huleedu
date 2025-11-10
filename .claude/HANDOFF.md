# Handoff: ENG5 NP Runner Execute-Mode Fixes

## Status: 🔄 IN PROGRESS
**Date**: 2025-11-10
**Session**: Fix Plan ENG5 NP Runner Execute-Mode Failures

### What Changed
- **Event Collector Hardening**: `scripts/cj_experiments_runners/eng5_np/kafka_flow.py` now validates envelope data with the typed Pydantic models (LLMComparisonResultV1, CJAssessmentCompletedV1, AssessmentResultV1) before dereferencing attributes, eliminating the `'dict' object has no attribute ...` crash when EventEnvelope returns raw dicts.
- **Async Content Upload Pipeline**: Added `content_upload.py`, CLI flag + settings, and inventory changes so execute mode uploads anchor/student essays to Content Service before composing CJ requests. Includes session cache keyed by checksum, semaphore-limited concurrency (default 10), and Docker compose wiring for `CONTENT_SERVICE_URL` + `depends_on`.
- **Essay Ref Updates**: `build_essay_refs()` now accepts a checksum→storage_id map and uses real storage IDs instead of synthetic `anchor::checksum` placeholders. New helper `apply_comparison_limit()` keeps the batching math centralized.

### Tests
- `pdm run pytest-root scripts/tests/test_eng5_np_content_upload.py`
- `pdm run pytest-root scripts/tests/test_eng5_np_runner.py`

### Remaining Follow-Ups
1. Run `pdm run eng5-runner --mode execute ...` against live stack to confirm execute-mode end-to-end (content upload + CJ callbacks) once Kafka/content service are online.
2. Coordinate with DS/ops on Content Service retention expectations; uploads currently single-shot (no retry/backoff yet).
3. Consider extending artefact manifest to record storage IDs alongside checksums for provenance.

---

# Handoff: ENG5 NP Runner Container Configuration Complete

## Status: ✅ COMPLETE

**Date**: 2025-11-10
**Session**: ENG5 NP Runner Containerization Fix

## Implementation Summary

### Issue
`pdm run eng5-runner` failed with `ModuleNotFoundError: No module named 'typer'` in containerized execution. Root causes:
1. **Dependency Mount Conflict**: `docker-compose.eng5-runner.yml` mounted entire repo (`./:/app:cached`), overwriting container's populated `__pypackages__/3.11/lib/` with host's empty directory
2. **Git Binary Missing**: `gather_git_sha()` raised uncaught `FileNotFoundError` when git binary unavailable in container

### Files Modified

**services/eng5_np_runner/Dockerfile** (20 LoC)
- Added standard environment variable block (`PDM_USE_VENV=false`, `PYTHONPATH=/app`, `ENV_TYPE=docker`)
- Implemented multi-stage build pattern matching other services
- Copied CLI scripts into image during build
- Separated `ENTRYPOINT`/`CMD` for proper argument handling

**docker-compose.eng5-runner.yml** (40 LoC)
- **Removed** `./:/app:cached` full repo mount (caused dependency overwrite)
- **Added** specific source mounts only:
  - `./scripts/cj_experiments_runners:/app/scripts/cj_experiments_runners:cached`
  - `./libs/common_core/src:/app/libs/common_core/src:cached`
  - `./libs/huleedu_service_libs/src:/app/libs/huleedu_service_libs/src:cached`
- Removed `PYTHONPATH` override (uses Dockerfile default `/app`)
- Added `DEPS_IMAGE` build arg for base image resolution

**scripts/cj_experiments_runners/eng5_np/environment.py:23** (1 LoC change)
- Changed `except subprocess.CalledProcessError:` to `except (subprocess.CalledProcessError, FileNotFoundError):`
- Handles missing git binary gracefully, returns `"UNKNOWN"` for metadata tracking

### Pattern Alignment

Solution follows established service containerization pattern:
- Dependencies installed in `/app/__pypackages__/3.11/lib/` during build (via `huledu-deps:dev` base image)
- Source code volume-mounted for hot-reload
- No dependency directories mounted from host
- Matches patterns in `cj_assessment_service`, `essay_lifecycle_service`, etc.

### Verification

✅ `pdm run eng5-runner --mode plan --batch-id test` completes successfully
✅ All Python dependencies accessible (typer, aiohttp, common_core, etc.)
✅ Git SHA gracefully falls back to "UNKNOWN" in containerized environment
✅ Asset inventory, validation logging, and runner orchestration functional

### Next Actions

Consult `Documentation/OPERATIONS/ENG5-NP-RUNBOOK.md` for execute-mode workflows. Runner container now ready for Phase 3.3 batch assessment execution.

---

# Previous Session: Phase 2.5 Complete - LLM Model Version Management

## Status: ✅ COMPLETE

**Date**: 2025-11-09
**Phase**: 2.5 - Integration Verification
**Task**: TASK-LLM-MODEL-VERSION-MANAGEMENT.md Phase 2.5

## Implementation Summary

### Files Created (782 LoC, 18 tests)
1. `services/cj_assessment_service/tests/integration/test_llm_provider_manifest_integration.py` (471 LoC, 6 integration tests)
2. `scripts/tests/test_eng5_np_manifest_integration.py` (311 LoC, 12 unit tests)

### Files Modified
1. `scripts/cj_experiments_runners/eng5_np/cli.py` - Fixed provider enum conversion bug (`.lower()` not `.upper()`), lines 45-169
2. `services/llm_provider_service/README.md` - Compressed integration documentation (235→33 LoC), removed deprecated content
3. `.claude/rules/020.13-llm-provider-service-architecture.mdc` - Added Section 1.5 Model Manifest patterns

## Test Results

- **CJ Integration**: 6/6 PASSED, 0 SKIPPED (with services running)
- **ENG5 Unit**: 12/12 PASSED
- **CJ Full Suite**: 456 passed, 3 skipped (no regressions)
- **Type Safety**: No new errors from Phase 2.5 changes (17 pre-existing in `test_admin_routes.py`)

## Compliance

- ✅ Architect review completed (lead-dev-code-reviewer agent)
- ✅ Rule 075/075.1 violations fixed:
  - Removed forbidden `capsys` log message testing
  - Added `mock.assert_called_once_with()` assertions
  - Converted to behavioral testing
- ✅ Rule 090 documentation standards applied (compressed, hyper-technical)
- ✅ All files < 500 LoC

## Integration Architecture

```
CLI/Batch Runner
  → validate_llm_overrides() [manifest query]
  → ELS_CJAssessmentRequestV1(llm_config_overrides)
  → Kafka
  → CJ Assessment Service
  → HTTP POST /api/v1/comparison
  → LLM Provider Service
  → LLMComparisonResultV1 callback (includes actual model/provider/cost metadata)
```

## Next Actions

- ENG5 runner now enforces metadata + schema compliance; consult `Documentation/OPERATIONS/ENG5-NP-RUNBOOK.md` for the execute-mode checklist.
- Architect brief (`TASKS/TASK-CJ-PHASE3-ARCHITECT-NEXT-SESSION.md`) stays as the coordination point for remaining Phase 3.3 validation + observability polish.
- Phase 2.5 remains complete; Phase 3.3 work proceeds per the brief + runbook.

## Session Summary (2025-11-09) – Phase 3.3 Metadata & Artefact Hardening

- **LLM Provider parity**: Added `prompt_utils.compute_prompt_sha256()` and updated the queue processor error path so every `LLMComparisonResultV1` now echoes `essay_a_id`/`essay_b_id` plus a deterministic `prompt_sha256`, even when the provider fails before returning metadata. `services/llm_provider_service/tests/unit/test_callback_publishing.py` now asserts the new behavior.
- **Runner guarantees**: `scripts/cj_experiments_runners/eng5_np/*` now fail fast on missing metadata, dedupe comparison callbacks, annotate runner status/partial data, and emit cost + prompt-hash summaries via the CLI. Artefacts are serialized as true document blobs (instructions/prompt contents, anchor/student records with SHA256s) and idempotent manifests.
- **Schema validation**: Added `jsonschema` dependency plus test coverage (`scripts/tests/test_eng5_np_runner.py`) to validate artefacts against `Documentation/schemas/eng5_np/assessment_run.schema.json` and to enforce the new behaviors (fail-fast, dedupe, timeout flags).
- **Operational doc**: Authored `Documentation/OPERATIONS/ENG5-NP-RUNBOOK.md`, covering prerequisites, command sequences, monitoring hooks, and failure/retry guidance for execute mode.
- **Tests executed**: `pdm run pytest-root services/llm_provider_service/tests/unit/test_callback_publishing.py` and `pdm run pytest-root scripts/tests/test_eng5_np_runner.py`.

## Critical Files for Next Developer

- Model Manifest: `services/llm_provider_service/model_manifest.py:74-350`
- CJ Client: `services/cj_assessment_service/implementations/llm_provider_service_client.py:44-234`
- CLI Validation: `scripts/cj_experiments_runners/eng5_np/cli.py:45-169`
- Integration Tests: `services/cj_assessment_service/tests/integration/test_llm_provider_manifest_integration.py`
- Architecture Rule: `.claude/rules/020.13-llm-provider-service-architecture.mdc`

## Session Summary (2025-11-09) – Phase 3.2 Typing & Test Hardening

**Status:** Cleared the remaining MyPy/test blockers for the CJ admin surface so Phase 3.2 can keep moving without type ignores.

### What Changed – Typing & Tests

- Added an `AssessmentInstructionStore` helper and updated every CJ repository mock (admin routes, shared mocks, anchor helpers, callback manager scenarios, workflow continuation, single-essay finalizer) to return concrete `AssessmentInstruction` objects with precise signatures—no residual `Any`.
- Tightened the CJ admin Typer CLI by introducing JSON type aliases plus a `TokenCache` `TypedDict`, ensuring `_load_cache`, `_refresh`, `_admin_request`, etc., all have concrete return types.
- Updated API Gateway middleware/providers to invoke the shared JWT helpers with the required keyword arguments (`correlation_id`, `service`, `operation`) so they satisfy the new signature, and added a dedicated `CorrelationContext` fixture to the Quart admin tests.

### Validation – Typing & Tests

- `pdm run typecheck-all`
- `pdm run pytest-root services/cj_assessment_service/tests/unit/test_admin_routes.py services/cj_assessment_service/tests/unit/test_admin_cli.py`
- `pdm run pytest-root services/cj_assessment_service/tests/unit/test_anchor_management_api_core.py services/cj_assessment_service/tests/unit/test_anchor_management_api_errors.py services/cj_assessment_service/tests/unit/test_anchor_management_api_validation.py services/cj_assessment_service/tests/unit/test_callback_state_manager.py services/cj_assessment_service/tests/unit/test_callback_state_manager_extended.py services/cj_assessment_service/tests/unit/test_workflow_continuation.py services/cj_assessment_service/tests/unit/test_single_essay_completion.py`

### Next Up

- Stitch the CJ admin CLI login flow into the staged Identity tokens for `dev` once credentials land, then resume the Phase 3.2 deliverables (Step 4 docs/observability).

## Session Update (2025-11-10) – ENG5 Runner container smoke test

- Added the dedicated runner image and override compose file (`services/eng5_np_runner/Dockerfile`, `docker-compose.eng5-runner.yml`) so `docker compose … eng5_np_runner` can wrap the Typer CLI.
- First `docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm eng5_np_runner --mode plan --batch-id eng5-plan-check` attempt recreated infrastructure containers; `kafka_topic_setup` exited `1` after exhausting retries with `KafkaConnectionError: Unable to bootstrap from [('kafka', 9092, <AddressFamily.AF_UNSPEC: 0>)]` because `kafka` was not resolvable yet inside the bootstrap container.
- Root cause: invoking the one-off runner while the Kafka/Zookeeper stack was still provisioning—Compose spins up dependencies on-demand, but the bootstrap job begins before Docker DNS has registered the `kafka` hostname on the shared network when the infra stack is cold.

### Next Steps

1. Pre-start infra and the topic bootstrap in detached mode:
   ```bash
   docker compose -f docker-compose.yml up -d kafka zookeeper redis
   docker compose -f docker-compose.yml up kafka_topic_setup
   ```
   Wait for `kafka_topic_setup` to finish successfully.
2. Re-run the runner container with the override file:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm eng5_np_runner --mode plan --batch-id eng5-plan-check
   ```
3. For dry plumbing checks (before Kafka is healthy), supply `--no-kafka` to skip publishing while still exercising structured logging.

## Session Summary (2025-11-09) – Phase 3.2 Prompt Architecture: Execute-Mode Validation

**Status:** Phase 3.2 is now functionally complete. Execute-mode artefacts are schema-compliant, ENG5 grade scales exhibit no drift, and pre-flight automation verifies all dependencies before runs. Documentation coverage sits at ~60%—runbook/HANDOFF/README updates remain.

### What Changed

- Added `services/cj_assessment_service/tests/integration/test_eng5_scale_flows.py` to assert ENG5 scale isolation, anchor filtering, and below-lowest grade behavior.
- Added `scripts/tests/test_eng5_np_execute_integration.py` to validate execute-mode hydrators, event hydration, artefact completeness, and timeout recovery.
- Patched `scripts/cj_experiments_runners/eng5_np/hydrator.py` so `_write_artefact()` re-serializes JSON after checksum computation, preventing schema regressions.
- Authored `scripts/eng5_np_preflight.sh` to validate Docker services, Kafka connectivity, CJ admin CLI access, and filesystem readiness prior to execute runs.
- Updated `documentation/OPERATIONS/ENG5-NP-RUNBOOK.md` with pre-flight requirements, Grafana dashboard references, and `jq` post-execution inspection snippets.

### Validation

- `pdm run pytest-root services/cj_assessment_service/tests/integration/test_eng5_scale_flows.py -v`
- `pdm run pytest-root scripts/tests/test_eng5_np_execute_integration.py -v`
- `pdm run typecheck-all`
- `bash scripts/eng5_np_preflight.sh`

### Remaining Dependencies for Phase 3.3

- Update service documentation: `services/llm_provider_service/README.md` (prompt_sha256 ownership) and `services/batch_conductor_service/README.md` (prompt_attached gating).
- Document `student_prompt_ref` expectations for downstream consumers in Result Aggregator docs.
- Add structured JSON logging to ENG5 runner components (`hydrator.py`, `kafka_flow.py`, `cli.py`) to aid execute-mode forensics.
- Complete documentation updates (`documentation/OPERATIONS/ENG5-NP-RUNBOOK.md` references done; pending runbook cross-links and Grafana playbook pointers) and mark Phase 3.2 as ✅ in task documents.

## Next Session Plan – Phase 3.3 Runner Completion

1. **Structured Logging Implementation**
   - Add JSON-formatted logs (std `logging` with shared formatter) to `scripts/cj_experiments_runners/eng5_np/{hydrator,kafka_flow,cli}.py` capturing execution mode, batch IDs, event counts, validation state, and error paths.
   - Ensure logs respect existing correlation ID propagation and can be toggled via CLI verbosity.
2. **Documentation Finalization**
   - Cross-link the ENG5 pre-flight script and new logging behavior in `documentation/OPERATIONS/ENG5-NP-RUNBOOK.md` and reference relevant Grafana panels per sections 51–62.
   - Mark Phase 3.2 as ✅ in `TASKS/phase3_cj_confidence/TASK-PHASE-3.2-PROMPT-ARCHITECTURE-IMPLEMENTATION.md` and update the parent task’s progress table.
3. **Observability Verification**
   - Validate that new logs appear in Loki with proper labels and that `huleedu_bcs_prompt_prerequisite_blocked_total` + runner metrics surface in Grafana dashboards.
   - Add any missing notes to `.claude/HANDOFF.md` if additional follow-up is required.

## Session Summary (2025-11-10) – Phase 3.3 Runner Logging & Observability

- `scripts/cj_experiments_runners/eng5_np/cli.py` now calls `log_validation_state()` for plan, dry-run, and execute paths using in-memory artefact data so we emit `runner_validation_state` logs even when JSON files are not present. @scripts/cj_experiments_runners/eng5_np/cli.py#321-455
- Runbook updated with container wrapper commands (`docker compose run eng5_np_runner …`), Loki queries, and local `tee` guidance to keep structured logs. @documentation/OPERATIONS/ENG5-NP-RUNBOOK.md#44-114
- Phase trackers updated: parent task records verification notes and Phase 3.2 task is marked complete with closing remarks. @TASKS/phase3_cj_confidence/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md#72-82 @TASKS/phase3_cj_confidence/TASK-PHASE-3.2-PROMPT-ARCHITECTURE-IMPLEMENTATION.md#1-144
- Validations run: `pdm run pytest-root scripts/tests/test_eng5_np_execute_integration.py -v`, `pdm run pytest-root services/cj_assessment_service/tests/integration/test_eng5_scale_flows.py -v`, `pdm run typecheck-all` (green). `bash scripts/eng5_np_preflight.sh` currently fails because `cj_assessment_service` container is stopped; remedy with `pdm run dev-start cj_assessment_service` before execute-mode runs.

## Session Summary (2025-11-09) – Phase 3.2 Typing & Test Hardening

**Status:** Cleared the remaining MyPy/test blockers for the CJ admin surface so Phase 3.2 can keep moving without type ignores.

### What Changed

- Added an `AssessmentInstructionStore` helper and updated every CJ repository mock (admin routes, shared mocks, anchor helpers, callback manager scenarios, workflow continuation, single-essay finalizer) to return concrete `AssessmentInstruction` objects with precise signatures—no residual `Any`.
- Tightened the CJ admin Typer CLI by introducing JSON type aliases plus a `TokenCache` `TypedDict`, ensuring `_load_cache`, `_refresh`, `_admin_request`, etc., all have concrete return types.
- Updated API Gateway middleware/providers to invoke the shared JWT helpers with the required keyword arguments (`correlation_id`, `service`, `operation`) so they satisfy the new signature.
- Added an explicit `CorrelationContext` fixture for the admin route tests so Dishka providers stay type-safe without inline mocks.

### Validation

- `pdm run typecheck-all`
- `pdm run pytest-root services/cj_assessment_service/tests/unit/test_admin_routes.py services/cj_assessment_service/tests/unit/test_admin_cli.py`
- `pdm run pytest-root services/cj_assessment_service/tests/unit/test_anchor_management_api_core.py services/cj_assessment_service/tests/unit/test_anchor_management_api_errors.py services/cj_assessment_service/tests/unit/test_anchor_management_api_validation.py services/cj_assessment_service/tests/unit/test_callback_state_manager.py services/cj_assessment_service/tests/unit/test_callback_state_manager_extended.py services/cj_assessment_service/tests/unit/test_workflow_continuation.py services/cj_assessment_service/tests/unit/test_single_essay_completion.py`

### Next Up

- Stitch the CJ admin CLI login flow into the staged Identity tokens for `dev` once credentials land, then resume the Phase 3.2 deliverables (Step 4 docs/observability).
