# Code Review: Phase-2 provider_batch_api Follow-Up

- Date: 2025-12-10
- Reviewer: GPT-5.1 (Codex CLI)
- Scope:
  - LPS BatchApiStrategy / QueuedRequestExecutor error-path semantics
  - CJ provider_batch_api metadata persistence and continuation guards
  - ENG5 / CJ runbook + TASK alignment for Phase-2

## LPS – BatchApiStrategy / QueuedRequestExecutor

- `BatchApiStrategy.execute(...)` forms bundles using the same compatibility rules as `SerialBundleStrategy`, updates queue status to `PROCESSING`, and records prompt-block metrics/trace metadata before dispatch.
- The BATCH_API path now wraps `schedule_job(...)` + `collect_results(...)` in a single `try` and:
  - On success, maps each `BatchJobResult` back to per-request callbacks via `ExecutionResultHandler.handle_request_success(...)`, preserving one callback per comparison.
  - On any exception (including `collect_results(...)` failures), logs a structured error with `queue_processing_mode="batch_api"`, raises a `HuleEduError` via `raise_processing_error(...)`, and routes every bundled request through `handle_request_hule_error(...)` exactly once, yielding per-request `ExecutionOutcome(result="failure")`.
- The exception guard returns a `SerialBundleResult` with outcomes for all bundled requests and no pending request; `QueuedRequestExecutor.execute_batch_api(...)` re-wraps this into the shared `SerialBundleResult`/`ExecutionOutcome` types so callers never see a different shape.
- Unit tests (`test_batch_api_strategy_handles_collect_results_exception`, `test_execute_batch_api_handles_job_manager_error`) explicitly cover job-manager failure paths:
  - Assert `schedule_job`/`collect_results` await semantics.
  - Assert zero success callbacks, one `handle_request_hule_error` per bundled request, and per-request `result=="failure"` with matching `queue_id`s.
- Queue metrics and logs consistently use `queue_processing_mode="batch_api"` through `QueueProcessorMetrics.queue_processing_mode` and the new error log; there are no code paths where a job-manager failure bypasses the error handler.
- Note: the `# pragma: no cover` comment on the Batch API exception guard is now outdated given the new tests; optional future clean-up would be to remove or narrow that pragma, but it is not correctness-impacting.

## CJ – provider_batch_api metadata & continuation

- `_prepare_batch_state(...)` now:
  - Updates `CJBatchStatusEnum.PERFORMING_COMPARISONS` as before.
  - Builds `metadata_updates` from `NormalizedComparisonRequest.budget_metadata()` (preserving the existing `"comparison_budget"` shape) and then adds `"llm_batching_mode": effective_batching_mode.value` alongside the existing fields.
  - Calls `merge_batch_processing_metadata(...)` with this merged payload so `CJBatchState.processing_metadata` records the effective mode per batch.
- Initial submission continues to emit `preferred_bundle_size` hints via `BatchingModeService.build_metadata_context(...)`, with `preferred_bundle_size=len(comparison_tasks)` and an upper cap enforced elsewhere (64).
- Unit tests in `test_llm_batching_metadata.py` confirm:
  - For default `LLMBatchingMode.SERIAL_BUNDLE`, `preferred_bundle_size` equals the wave size and is within `[1, 64]`, and `metadata_updates["llm_batching_mode"] == "serial_bundle"`.
  - For `LLMBatchingMode.PROVIDER_BATCH_API`, the orchestrator persists `"llm_batching_mode": "provider_batch_api"` into the metadata passed to `merge_batch_processing_metadata(...)`.
  - The `AsyncMock.await_args` guards (`await_args = merge_mock.await_args; assert await_args is not None`) match patterns used elsewhere in CJ tests and keep type-checkers happy without obscuring the assertions on `metadata_updates`.
- `_resolve_batching_mode(metadata, settings) -> LLMBatchingMode` correctly:
  - Prefers `metadata["llm_batching_mode"]` (string or enum).
  - Falls back to `settings.LLM_BATCHING_MODE` when metadata is missing/invalid.
  - Uses `LLMBatchingMode.SERIAL_BUNDLE` as a defensive default when settings are unset or mocked.
- `trigger_existing_workflow_continuation(...)` now threads the resolved `effective_batching_mode` into orchestration while leaving `ContinuationContext` and `decide(...)` pure and mode-agnostic:
  - RESAMPLING: `_can_attempt_resampling(ctx)` is only honored when `effective_batching_mode is not LLMBatchingMode.PROVIDER_BATCH_API`; provider-batch runs never enter the RESAMPLING branch.
  - REQUEST_MORE_COMPARISONS: when `decision is ContinuationDecision.REQUEST_MORE_COMPARISONS` and either `effective_batching_mode is LLMBatchingMode.PROVIDER_BATCH_API` or `ctx.pairs_remaining <= 0`, continuation logs and returns instead of calling `comparison_processing.request_additional_comparisons_for_batch(...)`.
  - FINALIZE_* branches remain unchanged and still rely on `ContinuationContext.should_finalize` / `should_fail_due_to_success_rate`, so serial_bundle and small-net PR‑2/PR‑7 semantics are preserved.
- New orchestration tests in `test_workflow_continuation_orchestration.py` validate provider-batch behaviour:
  - `test_trigger_continuation_provider_batch_api_finalizes_without_requesting_more` exercises the “callbacks at cap, non-zero budget” path and asserts that `BatchFinalizer.finalize_scoring` is called while `request_additional_comparisons_for_batch` is never awaited.
  - `test_trigger_continuation_provider_batch_api_ignores_stability_flag` forces an unstable score delta so `decide(...)` would ordinarily request more comparisons; the new guard prevents any additional waves from being enqueued, and `request_additional_comparisons_for_batch` remains un-awaited.
- Existing serial_bundle and small-net tests (`test_workflow_continuation_success_rate.py`, `test_workflow_small_net_resampling.py`) remain semantically aligned:
  - In the absence of `llm_batching_mode` metadata, `_resolve_batching_mode(...)` defaults to SERIAL_BUNDLE, so the new guards never fire and the prior resampling/continuation behaviour is unchanged.
  - Small-net Phase‑2 resampling still uses `_can_attempt_small_net_resampling(...)` and respects resampling caps; regular nets continue to gate resampling on full coverage and the regular-batch cap.
- The choice to keep LLMBatchingMode-specific behaviour in `workflow_continuation` (rather than threading mode into `ContinuationContext`/`decide`) feels like an appropriate abstraction boundary for this slice: it localises provider_batch_api semantics to orchestration without risking cross-mode regressions. If future modes need different notions of “finalize vs request more”, it may then be worth threading mode into the context and making `decide(...)` explicitly mode-aware.

## Docs & TASK alignment

- `docs/operations/eng5-np-runbook.md`:
  - LPS Phase‑2 section explicitly describes `QueueProcessingMode.BATCH_API` as a dedicated `BatchApiStrategy` + `BatchJobManager` path that still emits one callback per comparison, matching the current `BatchApiStrategy.execute(...)` + `ExecutionResultHandler` wiring.
  - CJ semantics for `provider_batch_api` now match code: `llm_batching_mode` is persisted into `CJBatchState.processing_metadata`, continuation reads this mode, and **no additional comparison waves are scheduled** once the initial provider batch wave has been submitted; finalization remains cap/denominator-driven, with single-wave “all-at-once to cap” semantics deferred to a follow-up slice.
  - Metrics references (`queue_processing_mode="batch_api"` for queue metrics and job-level metrics placeholders) are consistent with `QueueProcessorMetrics` and the current BATCH_API execution path; job-level metrics remain a TODO as per the Phase‑2 checklist.
- `docs/operations/cj-assessment-runbook.md`:
  - The “CJ LLM batching modes” section correctly differentiates `per_request`, `serial_bundle`, and `provider_batch_api`, including:
    - Metadata persistence of `"llm_batching_mode"`.
    - The guarantee that `workflow_continuation` never calls `request_additional_comparisons_for_batch(...)` in provider-batch mode.
    - The fact that stability is diagnostic in this mode and no longer a trigger for additional waves.
- `TASKS/integrations/llm-provider-batch-api-phase-2.md`:
  - Phase 2.3 is updated to `[x]` with specific references to:
    - The new BATCH_API queue strategy (`BatchApiStrategy` + `QueuedRequestExecutor.execute_batch_api(...)`).
    - The two new LPS tests covering job-manager failure guards.
  - Phase 2.4:
    - Marks `llm_batching_mode` persistence as `[x]` and references the CJ batching metadata tests.
    - Marks continuation semantics as `[~]`, accurately describing the new guards that finalize on caps and prevent additional waves in `provider_batch_api` while leaving “single-wave generation up to max_pairs_cap” for a later slice.
- `TASKS/assessment/cj-llm-provider-batch-api-mode.md`:
  - PR1 progress notes align with the current `_prepare_batch_state(...)` and metadata tests, including serial vs provider-batch `llm_batching_mode` values.
  - PR2 progress notes match the implemented `_resolve_batching_mode(...)` and the guarded continuation branches, with explicit references to the new orchestration tests verifying that provider-batch runs finalize without resampling or additional coverage waves.

## Pain points / considerations

- `AsyncMock.await_args` guards in the new CJ tests follow an existing pattern in this codebase and are reasonable for type safety; no changes recommended.
- Continuation semantics layering (mode-aware guards at the orchestration layer, pure `ContinuationContext`/`decide` logic) strikes a good balance between safety and clarity for this phase; if future work needs mode-specific `should_finalize` rules, threading mode into the context would be the next logical step.
- Negative-path LPS tests intentionally trigger `RuntimeError` in job-manager mocks; the resulting stack traces in pytest output are acceptable given:
  - The application-level guards swallow these exceptions and emit structured logs instead of failing the tests.
  - The traces are useful regression signals if defensive error handling ever stops working.
