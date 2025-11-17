---
id: "cj-prompt-context-persistence-plan"
title: "✅ COMPLETED (2025-11-12)"
type: "task"
status: "research"
priority: "medium"
domain: "integrations"
service: ""
owner_team: "agents"
owner: ""
program: ""
created: "2025-11-16"
last_updated: "2025-11-17"
related: []
labels: []
---
**Status**: All phases (1-9) complete and merged to main

**Commits**:

- `32e14a0e` feat(cj): implement prompt context persistence hardening
- `86317e8c` fix(eng5-runner): correct storage ID format and batch validation
- `9d48d01f` style: apply auto-formatting and update handoff documentation

**Test Results**: 31/31 passing | Typecheck clean (all CJ service errors resolved)

**Implementation Summary**:

- Added `Result[T,E]` monad for typed success/failure handling
- Created `PromptHydrationFailure` dataclass for error payloads
- Implemented `CJProcessingMetadata` Pydantic model for typed metadata overlay
- Event processor returns `Result[str, PromptHydrationFailure]` from hydration
- Batch preparation: Fallback to Content Service hydration, typed metadata merge preserves unknown keys
- Metrics: Added `prompt_fetch_success` counter alongside existing failures counter
- Repository: Returns `student_prompt_storage_id` for workflow synchronization

**Files Modified**:

- Core: `models_api.py`, `event_processor.py`, `batch_preparation.py`, `workflow_orchestrator.py`, `db_access_impl.py`, `pair_generation.py`, `metrics.py`
- Tests: 5 updated files, 2 new test files (test_event_processor_prompt_context.py, test_prompt_metrics.py)

**Follow-up Work** (Codebase Consolidation - Separate Task):

- Result[T,E] consolidation into huleedu_service_libs (eliminates 3+ local implementations across services)
- JWT test helpers centralization (shared utilities for test token creation)
- DI re-alignment with pure `_impl` pattern (restore Rule 042 compliance)

**See**: `.claude/rules/048-structured-error-handling-standards.md` for Result monad usage guidelines (to be added)

---

# CJ Prompt Context Persistence Hardening Plan

## Overview

This plan delivers a single refactor pass across the CJ Assessment Service to harden student prompt propagation, enforce typed metadata, and improve hydration observability. The refactor intentionally omits backwards-compatibility flags and executes as one atomic commit.

## Problem Summary

Silent prompt-context loss is occurring across the event ➝ batch ➝ pair-generation flow due to four coupled issues:

1. `assignment_id` never reaches the batch-prep layer because the event processor drops it.
2. Prompt hydration succeeds inconsistently; empty strings and fetch errors collapse to `None` without diagnostics.
3. Anchor resolvers cannot access student prompts if metadata is missing or malformed.
4. `CJBatchUpload.processing_metadata` accepts arbitrary dicts, inviting schema drift and clobbering other workflow keys during updates.

## Guiding Principles

- **Strict DI threading**: Every dependency (especially the content client) is passed explicitly through call stacks and fixtures.
- **Typed metadata, permissive merge**: Known keys get first-class models, but existing unknown keys remain untouched when merging.
- **Result-based hydration**: Prompt fetch operations return discriminated results that callers must inspect.
- **Telemetry reuse**: Extend existing metrics instead of creating parallel collectors.
- **Comprehensive tests**: Update unit and integration fixtures in lockstep with signature changes.

## Phases

### Phase 1 – Shared Types & Helpers

1. **Prompt hydration failure payload**
   - Location: `services/cj_assessment_service/models_api.py`
   - Add frozen dataclass `PromptHydrationFailure` with fields `reason: str` and `storage_id: str | None`.
   - Reasons must cover: `empty_content`, `content_service_error`, `unexpected_error`.

2. **Result union**
   - Same file: introduce lightweight generic `Result[T, E]` with helpers `ok(...)`, `err(...)`, `is_ok`, `is_err`, and safe accessors (`value`, `error`).
   - Keep implementation minimal to avoid external dependency.

3. **Typed metadata model**
   - Add `CJProcessingMetadata(BaseModel)` with optional `student_prompt_storage_id` and `student_prompt_text`.
   - Configure `ConfigDict(extra="forbid")` and rely on `.model_dump(exclude_none=True)` before merging.

### Phase 2 – Event Processor Fixes

1. **Propagate assignment id**
   - File: `services/cj_assessment_service/event_processor.py`
   - Add `assignment_id` to `converted_request_data` so downstream phases receive it.

2. **Result-returning hydrator**
   - Update `_hydrate_prompt_text(...)` to return `Result[str, PromptHydrationFailure]`.
   - Behaviour:
     - If `storage_id` is `None`, return `Result.ok(None)` (no prompt supplied is not a failure).
     - On success with non-empty content: log debug, increment success metric, `Result.ok(text)`.
     - On empty string: record failure reason `empty_content`, return `Result.err(PromptHydrationFailure(...))`.
     - On `HuleEduError`: record failure reason `content_service_error` with storage id.
     - On unexpected exceptions: record failure reason `unexpected_error`.

3. **Caller updates**
   - Event processor should unpack the result, defaulting `prompt_text` to `None` on errors, and only increment success metrics when `result.is_ok and result.value`.

### Phase 3 – Batch Preparation Refactor

1. **Signature change**
   - File: `services/cj_assessment_service/cj_core_logic/batch_preparation.py`
   - Extend `create_cj_batch(...)` to accept a required `content_client: ContentClientProtocol` argument.

2. **Hydration fallback**
   - After assignment-based auto-hydration, if `prompt_storage_id` exists but `prompt_text` is falsy, fetch via `content_client.fetch_content(...)`.
   - On success: log informational message, bump success metric (shared helper).
   - On failure: log error with storage id, allow workflow to continue with `None`.

3. **Metadata merge**
   - Instantiate `CJProcessingMetadata` when either prompt field is present.
   - Merge using:

     ```python
     existing_metadata = cj_batch.processing_metadata or {}
     typed_metadata = CJProcessingMetadata(...).model_dump(exclude_none=True)
     cj_batch.processing_metadata = {**existing_metadata, **typed_metadata}
     ```

   - Flush session after assignment.

### Phase 4 – Call-Site Threading

1. **Workflow orchestrator**
   - File: `services/cj_assessment_service/cj_core_logic/workflow_orchestrator.py`
   - Pass the `content_client` argument into `create_cj_batch`.

2. **Tests & fixtures**
   - Extend `services/cj_assessment_service/tests/fixtures/database_fixtures.py` (or `tests/conftest.py`) with a `mock_content_client` fixture returning an `AsyncMock` that satisfies `ContentClientProtocol`.
   - Import this fixture where needed; do not create a new fixtures module.
   - Update every direct call to `create_cj_batch` (9 unit tests, 2 integration tests) to supply `content_client`.

### Phase 5 – Repository Contract

- File: `services/cj_assessment_service/implementations/db_access_impl.py`
- Ensure `get_assignment_context` returns `student_prompt_storage_id` so anchor workflows can hydrate prompts.

### Phase 6 – Pair Generation Safeguards

- File: `services/cj_assessment_service/cj_core_logic/pair_generation.py`
  - Parse metadata using typed model if available.
  - Emit a warning with correlation/batch ids when both instructions and student prompt are missing.

### Phase 7 – Metrics Enhancements

1. **Reuse existing counters**
   - File: `services/cj_assessment_service/metrics.py`
   - Extend `prompt_fetch_failures` counter with new labels: `empty_content`, `content_service_error`, `unexpected_error`, `batch_creation_hydration_failed`.
   - Add a companion counter `prompt_fetch_success_total` for successful hydrations.

2. **Instrumentation points**
   - Event processor hydration path.
   - Batch-preparation hydration fallback.

### Phase 8 – Testing Additions

1. **Metadata merge test**
   - File: `services/cj_assessment_service/tests/unit/test_batch_preparation_identity_flow.py`
   - Assert existing metadata keys persist after calling `create_cj_batch` with new prompt fields.

2. **Hydration result coverage**
   - File: `services/cj_assessment_service/tests/unit/test_event_processor.py`
   - Cover `Result` behaviour for `None` storage id, empty content, content service errors, and unexpected exceptions.

3. **Typed metadata usage**
   - Update `test_pair_generation_context.py` fixtures to build metadata via `CJProcessingMetadata`.

4. **Integration adjustments**
   - Update `test_student_prompt_workflow.py` to inject the mocked content client or a test implementation consistent with the new signature.

### Phase 9 – Validation Runbook

After implementation:

1. `pdm run typecheck-all`
2. `pdm run pytest-root services/cj_assessment_service/tests -q`
3. Register 12 anchors via CLI and confirm prompts/instructions persist in DB.
4. Inspect service logs for `Fetched assessment context` with both flags true.
5. Confirm generated LLM prompts contain both “Assignment Prompt:” and “Assessment Criteria:” sections.
6. Verify `prompt_fetch_success_total` and `prompt_fetch_failures_total{reason="..."}` increment as expected.

## Risks & Mitigations

- **Breaking signature**: All `create_cj_batch` call sites and fixtures must be updated simultaneously.
- **Metric duplication**: Ensure only existing counters are extended; no new metric names for failures to avoid duplication.
- **Error taxonomy drift**: Reuse `create_error_detail_with_context` when raising `HuleEduError` elsewhere to stay aligned with platform standards.

## Deliverables

- Updated service implementation across event processor, batch prep, orchestrator, repository, pair generation, and metrics modules.
- New `PromptHydrationFailure`, `Result[T, E]`, and `CJProcessingMetadata` plus supporting unit tests.
- Extended fixtures and integration tests reflecting the dependency injection changes.
- Updated `.claude/work/session/handoff.md` (already done) with plan summary for cross-session visibility.
