---
id: staged-submission-cj-2025-11-27
type: code-review
subject: "Priority 3 – Staged Submission for CJ (serial bundles, non-batch-API)"
created: 2025-11-27
last_updated: 2025-11-27
status: in_progress
---
# Code Review: Staged Submission for CJ (Priority 3)

## Scope

- CJ Assessment Service staged submission for serial-bundle / non-batch-API modes.
- Files inspected so far:
  - `TASKS/infrastructure/persist-text-storage-id-on-file-uploads-and-enable-mock-llm-for-functional-cj.md`
  - `docs/operations/cj-assessment-foundation.md` (Planned PR: staged submission)
  - `docs/decisions/0017-cj-assessment-wave-submission-pattern.md`
  - `docs/product/epics/cj-assessment-epic.md`
  - `services/cj_assessment_service/config.py`
  - `services/cj_assessment_service/cj_core_logic/comparison_processing.py`
  - `services/cj_assessment_service/cj_core_logic/comparison_batch_orchestrator.py`
  - `services/cj_assessment_service/cj_core_logic/llm_batching_service.py`
  - `services/cj_assessment_service/cj_core_logic/llm_batching.py`
  - `services/cj_assessment_service/cj_core_logic/batch_processor.py`
  - `services/cj_assessment_service/models_db.py` (CJBatchState + related models)
  - `services/cj_assessment_service/cj_core_logic/workflow_continuation.py`
  - `services/cj_assessment_service/cj_core_logic/pair_generation.py`
  - `services/cj_assessment_service/cj_core_logic/scoring_ranking.py`
  - `services/cj_assessment_service/implementations/llm_interaction_impl.py`
  - `services/cj_assessment_service/message_handlers/llm_callback_handler.py`
  - `services/cj_assessment_service/cj_core_logic/batch_callback_handler.py`
  - `services/cj_assessment_service/batch_monitor.py`
  - `services/cj_assessment_service/tests/unit/test_comparison_processing.py`
  - `services/cj_assessment_service/tests/unit/test_workflow_continuation.py`

## Initial Findings (Phase 1 – Understanding Only)

- The current implementation already has a callback-driven, stability-aware continuation loop:
  - `batch_processor._update_batch_state_with_totals()` tracks `total_budget`, `total_comparisons`,
    `submitted_comparisons`, and `current_iteration` per CJ batch.
  - `workflow_continuation.trigger_existing_workflow_continuation()` runs after each callback
    iteration (via `batch_callback_handler.continue_cj_assessment_workflow()`), recomputes BT
    scores using `scoring_ranking.record_comparisons_and_update_scores(...)`, checks stability via
    `scoring_ranking.check_score_stability(...)` plus `MIN_COMPARISONS_FOR_STABILITY_CHECK` and
    `SCORE_STABILITY_THRESHOLD`, and then either:
    - finalizes the batch immediately (stability, budget exhausted, or callbacks hitting the
      completion denominator), or
    - calls `comparison_processing.request_additional_comparisons_for_batch(...)` to enqueue
      another iteration.
- Pair generation is already effectively *staged*:
  - `comparison_batch_orchestrator.submit_initial_batch()` and the continuation path both call
    `pair_generation.generate_comparison_tasks(...)` with:
    - `existing_pairs_threshold=settings.COMPARISONS_PER_STABILITY_CHECK_ITERATION`
    - an explicit `max_pairwise_comparisons` cap derived from `ComparisonRequestNormalizer`.
  - `generate_comparison_tasks()`:
    - queries existing `cj_comparison_pairs` for the batch to avoid duplicates,
    - enforces the global `max_pairwise_comparisons` cap, and
    - generates at most `COMPARISONS_PER_STABILITY_CHECK_ITERATION` *new* pairs per iteration
      (subject to remaining budget).
  - This already behaves like “waves of comparisons” sized by `COMPARISONS_PER_STABILITY_CHECK_ITERATION`
    and guarded by `MAX_PAIRWISE_COMPARISONS`, even before we introduce a separate
    `MAX_BUNDLES_PER_WAVE` knob.
- Stability configuration and helpers are in place and used:
  - `Settings` defines `MIN_COMPARISONS_FOR_STABILITY_CHECK`, `SCORE_STABILITY_THRESHOLD`,
    and `COMPARISONS_PER_STABILITY_CHECK_ITERATION`, with documentation in the CJ README and
    comments marking them as part of the intended iterative loop.
  - `scoring_ranking.check_score_stability(...)` returns the max BT-score delta; current
    continuation logic in `workflow_continuation` uses this value plus the min-comparisons gate
    to compute `stability_passed`.
  - Batch metadata already persists `bt_scores`, `last_scored_iteration`, and `last_score_change`
    via `merge_batch_processing_metadata(...)`, providing the previous-iteration scores needed for
    stability checks.
- Wave semantics and LLM batching integration:
  - From CJ’s perspective, each call to `BatchProcessor.submit_comparison_batch(...)` is one
    “wave” of comparisons; `CJBatchState.current_iteration` is incremented per submission.
  - `BatchingModeService` and `llm_batching.build_llm_metadata_context(...)` add
    `cj_llm_batching_mode` and optional `comparison_iteration` metadata when
    `ENABLE_LLM_BATCHING_METADATA_HINTS` and `ENABLE_ITERATIVE_BATCHING_LOOP` are enabled, and
    when `LLM_BATCHING_MODE != per_request`. This is consistent with the serial-bundle rollout
    docs and Eng5 runbook.
  - `LLMInteractionImpl` always issues per-request calls to LPS, but the metadata hints
    (`cj_llm_batching_mode`, `comparison_iteration`) are sufficient for LPS’ queue to apply its
    own `serial_bundle` and provider-batch behaviours as described in the LPS tasks.
- Result surface and downstream dependencies:
  - The staged submission loop is isolated to CJ’s internal comparison scheduling; completion
    still flows through `BatchFinalizer` and dual event publishing to RAS.
  - RAS remains the source of truth for CJ results (as documented in
    `.claude/work/session/readme-first.md` and the CJ runbook), so staged submissions do not
    affect the ENG5/guest result surface assumptions.

## Notable Gaps / Assumptions to Validate with User Before Coding

- `MAX_BUNDLES_PER_WAVE` is **not yet defined in `Settings` or used in code**:
  - All current staging is expressed in terms of “comparisons per iteration”
    (`COMPARISONS_PER_STABILITY_CHECK_ITERATION`) and a global `MAX_PAIRWISE_COMPARISONS` cap.
  - The ADR and task docs talk about “bundles per wave”; on the CJ side, the natural control point
    is “comparisons per wave”, not the provider’s internal bundle size. This is compatible with
    serial-bundle semantics (LPS does the bundling), but means `MAX_BUNDLES_PER_WAVE` will
    effectively be a cap on *comparisons* per wave from CJ’s perspective.
- `enforce_full_budget` flag is computed but **not honoured**:
  - `_resolve_comparison_budget()` in `workflow_continuation.py` returns `(max_pairs, enforce_full_budget)`
    where `enforce_full_budget` is `True` when the budget source is `"runner_override"`.
  - This flag is never used when deciding `should_finalize`; stability can currently stop a batch
    early even when a caller requested a specific `max_comparisons_override`. If ENG5 or other
    runners rely on “always use the full budget when overridden”, we will need an explicit
    decision here before tightening staged submission semantics.
- Iterative loop feature flag vs. actual behaviour:
  - The “iterative loop online” condition in the CJ README is currently used only to control
    metadata hints (`comparison_iteration`), not whether we actually perform stability-based
    continuation; the continuation path already recomputes scores and may enqueue more work on
    every fully-callback-complete iteration.
  - For the staged-submission PR we should clarify whether:
    - the continuation behaviour is always on (current state), and the flag only affects metadata, or
    - certain behaviours (e.g., iteration limits via `MAX_ITERATIONS`) should be gated behind
      `ENABLE_ITERATIVE_BATCHING_LOOP`.
- Test coverage for stability-driven early stop:
  - `test_workflow_continuation.py` already covers:
    - finalization when callbacks hit the completion denominator, and
    - requesting more comparisons when not finalized.
  - There is **no focused unit test that finalizes purely on stability before hitting the
    denominator or budget exhaustion**, and no tests that would enforce a future
    `MAX_BUNDLES_PER_WAVE` cap or “stability-based pacing” semantics. These are good candidates
    for the new tests the task calls for.

## Questions for User Alignment

1. For runs that set `max_comparisons_override` (e.g., ENG5 CLI runner), should the system:
   - continue to be **stability-first** (early stop allowed), or
   - treat those as “must consume full budget” and disable stability-based early stop for that
     batch?
2. On the CJ side, is it acceptable for `MAX_BUNDLES_PER_WAVE` to effectively mean “maximum
   *comparisons* per wave”, while LLM Provider Service handles the true request bundling based on
   metadata (`cj_llm_batching_mode = serial_bundle`), rather than CJ explicitly grouping items
   into provider-level bundles?
3. Do we want staged submission to apply only when `LLM_BATCHING_MODE` is `serial_bundle` /
   `provider_batch_api`, or should the same wave+stability pattern remain active in `per_request`
   mode as a safety net for smaller tenants and non-ENG5 flows?
