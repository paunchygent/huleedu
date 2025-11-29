# HANDOFF: Current Session Context

## Purpose

This document contains ONLY current/next-session work. All completed tasks, architectural decisions, and patterns are documented in:

- **README_FIRST.md** - Architectural overview, decisions, service status
- **Service READMEs** - Service-specific patterns, error handling, testing
- **.claude/rules/** - Implementation standards and requirements
- **Documentation/OPERATIONS/** - Operational runbooks (see docs/operations/cj-assessment-runbook.md for CJ/LLM defaults & metrics)
- **TASKS/** - Detailed task documentation

---

## 🎯 ACTIVE WORK (2025-11-29)

### PR-3: BT Standard Error Diagnostics & Observability (IN PROGRESS)

- Implemented a named constant `BT_STANDARD_ERROR_MAX = 2.0` in
  `services/cj_assessment_service/cj_core_logic/bt_inference.py` and updated
  `compute_bt_standard_errors` to:
  - Keep existing Fisher Information / pseudoinverse behaviour intact.
  - Cap reported SE values at the constant purely for numerical safety and
    observability (no change to completion, stability, or success-rate guards).
- Extended `record_comparisons_and_update_scores` in
  `services/cj_assessment_service/cj_core_logic/scoring_ranking.py` to compute
  a batch-level SE diagnostics summary after BT scores/SEs are computed:
  - `mean_se`, `max_se`, `min_se`
  - `item_count`, `comparison_count`
  - `items_at_cap`, `isolated_items`
  - `mean_comparisons_per_item`, `min_comparisons_per_item`,
    `max_comparisons_per_item`
  - Logs these fields alongside `cj_batch_id` and `correlation_id` for
    observability, without introducing additional writes or locks on
    `CJBatchState` (to avoid interfering with existing transaction patterns in
    callback/incremental-scoring flows).
- Updated `GradeProjector` in
  `services/cj_assessment_service/cj_core_logic/grade_projector.py` to compute
  a rankings-based SE summary split by cohort:
  - `"all"`, `"anchors"`, `"students"` each expose `mean_se`, `max_se`,
    `min_se`, `item_count`.
  - Threaded this summary into `GradeProjectionSummary.calibration_info` under
    `bt_se_summary` for downstream diagnostics (RAS/EPIC‑006) without changing
    grade assignment or completion behaviour.
- Added tests:
  - `services/cj_assessment_service/tests/unit/test_bt_inference.py` to assert
    that `compute_bt_standard_errors` respects `BT_STANDARD_ERROR_MAX`.
  - Extended `test_bt_standard_errors` in
    `services/cj_assessment_service/tests/integration/test_bt_scoring_integration.py`
    to verify `CJBatchState.processing_metadata["bt_se_summary"]` is present
    with the expected keys.
  - Extended `services/cj_assessment_service/tests/unit/test_grade_projector_system.py`
    to assert that `GradeProjectionSummary.calibration_info["bt_se_summary"]`
    exposes `all/anchors/students` aggregates.
- Documentation:
  - `docs/product/epics/cj-stability-and-reliability.md` updated with a PR‑3
    notes section describing:
    - Where BT SE caps are defined (`BT_STANDARD_ERROR_MAX`).
    - What SE metadata is now logged and persisted at batch level and in grade
      projection summaries.
    - Explicit statement that PR‑3 is observability-only (no change to PR‑2
      gating semantics or planned PR‑7 resampling behaviour).

Follow-ups for EPIC‑006 / future PRs (not implemented in PR‑3):
- Introduce health/quality indicators that consume `bt_se_summary` (e.g.,
  surface “low coverage / high SE” warnings in CJ/RAS surfaces).
- Consider exposing a lightweight batch-quality metric to ENG5 runners based
  on `items_at_cap`, `isolated_items`, and per-item comparison counts.

### PR-4: CJ Scoring Core Refactor (BT inference robustness) (IMPLEMENTATION COMPLETE, AWAITING REVIEW)

- Added `BTScoringResult` domain dataclass in `scoring_ranking.py` to capture BT scores, per‑essay SEs (capped at `BT_STANDARD_ERROR_MAX`), per‑essay comparison counts, and a batch‑level SE diagnostics summary.
- Introduced pure helper `compute_bt_scores_and_se(all_essays, comparisons) -> BTScoringResult` that:
  - Builds the BT graph from `EssayForComparison` + `CJ_ComparisonPair` rows.
  - Delegates to `choix.ilsr_pairwise` + `bt_inference.compute_bt_standard_errors`.
  - Mean‑centres scores and raises the existing CJ domain errors (`raise_cj_insufficient_comparisons`, `raise_cj_score_convergence_failed`) on insufficient data or numerical BT failures.
- Refactored `record_comparisons_and_update_scores(...)` to:
  - Use a single `SessionProviderProtocol` session to persist new `CJ_ComparisonPair` rows, reload all valid comparisons, update `CJ_ProcessedEssay` scores/SEs/counts via `_update_essay_scores_in_database(...)`, and commit once.
  - Delegate BT math to `compute_bt_scores_and_se` and emit PR‑3 style SE diagnostics logs (`mean_se`, `max_se`, `min_se`, `item_count`, `comparison_count`, `items_at_cap`, `isolated_items`, comparison‑per‑item stats) with `cj_batch_id` and `correlation_id`.
  - Return `dict[str, float]` BT scores so PR‑2 stability/success‑rate gating in `workflow_continuation` and `BatchFinalizer` remains unchanged.
- Confirmed no `CJBatchState` writes or nested sessions occur inside `scoring_ranking` (all state writes remain owned by workflow/finalizer/monitor code), eliminating the PR‑3 deadlock pattern from nested `merge_batch_processing_metadata` calls.
- Threaded `BTScoringResult.se_summary` into `CJBatchState.processing_metadata["bt_se_summary"]` from `trigger_existing_workflow_continuation` (same session owner), keeping BT SE diagnostics available for EPIC‑006 without changing completion/stability semantics.
- Added focused unit coverage for the helper and workflow metadata wiring:
  - `services/cj_assessment_service/tests/unit/test_scoring_ranking_bt_helper.py`
  - `services/cj_assessment_service/tests/unit/test_workflow_continuation.py::test_trigger_continuation_metadata_serializable_without_previous_scores`
- Re‑ran full CJ service tests plus repo‑wide quality gates:
  - `pdm run pytest-root services/cj_assessment_service/tests`
  - `pdm run format-all`, `pdm run lint-fix --unsafe-fixes`, `pdm run typecheck-all` (all green).

### BT SE Batch Quality Indicators (EPIC‑005/EPIC‑006 bridge) (IN PROGRESS)

- Added CJ service settings for **diagnostic-only** BT SE and coverage thresholds in
  `services/cj_assessment_service/config.py`:
  - `BT_MEAN_SE_WARN_THRESHOLD`, `BT_MAX_SE_WARN_THRESHOLD`
  - `BT_MIN_MEAN_COMPARISONS_PER_ITEM`
- Extended `trigger_existing_workflow_continuation` to derive batch-level **BT SE diagnostics**
  from `BTScoringResult.se_summary` without changing PR‑2 gating semantics:
  - `bt_se_inflated` – mean or max BT SE above diagnostic thresholds
  - `comparison_coverage_sparse` – mean comparisons per essay below a diagnostic floor
  - `has_isolated_items` – one or more isolated essays in the comparison graph
- Persist these as `bt_quality_flags` alongside `bt_se_summary` on
  `CJBatchState.processing_metadata` via `merge_batch_processing_metadata`, keeping ownership
  of `CJBatchState` writes in the workflow layer (scoring core remains pure/DB‑free).
- Updated the “Callback iteration complete; evaluated stability” log in
  `workflow_continuation.py` to include the three batch quality flags for observability:
  `bt_se_inflated`, `comparison_coverage_sparse`, `has_isolated_items`.
- Added focused unit coverage in
  `services/cj_assessment_service/tests/unit/test_workflow_continuation.py::test_bt_quality_flags_derived_from_bt_se_summary`
  to assert:
  - Flags are derived correctly for normal vs inflated SE, sparse coverage, and isolated items.
  - `metadata_updates` (including `bt_se_summary` and `bt_quality_flags`) is JSON-serializable
    (no NaN/Inf) using `json.dumps`.
- Documentation updates:
  - `docs/product/epics/cj-stability-and-reliability.md` now documents `bt_quality_flags` as
    observability-only BT SE diagnostics.
  - `docs/product/epics/cj-grade-projection-quality.md` references `bt_se_summary` and
    `bt_quality_flags` as the canonical batch-level SE/coverage indicators for grade
    projection quality analysis, without changing finalization or grade assignment rules.
  - `docs/operations/cj-assessment-runbook.md` now includes an ops-facing section on interpreting
    `bt_se_summary` / `bt_quality_flags` and the new Prometheus counters
    (`cj_bt_se_inflated_batches_total`, `cj_bt_sparse_coverage_batches_total`) as diagnostics
    only (no new gating).

### ENG5 Runner Refactoring (Anchor Alignment Experiment) (2025-11-29, COMPLETE)

**Context:** `cli.py` grew to 926 lines, violating 400-500 LoC limit. Refactored to handler-based architecture.

**Completed:**
- cli.py reduced from 926 → 569 lines (handler dispatch pattern)
- `--assignment-id` now optional (required only for EXECUTE mode)
- Test infrastructure: `tests/test_helpers/` with fixtures.py, builders.py
- 51 unit tests for `alignment_report.py` (all passing)
- Protocol definitions: `protocols.py` with `ModeHandlerProtocol`
- Handler dispatch via `HANDLER_MAP` constant
- Handler implementations:
  - `plan_handler.py` (103 lines) ✓
  - `dry_run_handler.py` (73 lines) ✓
  - `anchor_align_handler.py` (251 lines) - Over 200 limit (future improvement)
  - `execute_handler.py` (342 lines) - Over 200 limit (future improvement)
- typecheck-all passes ✓
- lint passes ✓

**Outstanding (lower priority):**
- Handler unit tests
- CLI integration tests with Typer CliRunner
- Split large handlers to meet 200-line target

**READY FOR BASELINE EXPERIMENT**

**Task Document:** `TASKS/assessment/anchor-alignment-prompt-tuning-experiment.md`

### ENG5-NP Runner Debug Complete (2025-11-29)

**Issue:** `ValueError: Comparison callback missing essay identifiers; correlation=7fd9e895-94e3-480b-b06d-906f6167c2fb`

**Root Cause:** Stale orphaned Kafka callbacks from prior test runs (Nov 28) contained incomplete metadata—only `resolved_provider`, `queue_processing_mode`, `prompt_sha256` but no `essay_a_id`/`essay_b_id`.

**Fix Applied:**
1. Deleted and recreated Kafka topics to clear stale events
2. Restarted all services to reset consumer group offsets (consumer groups pointed to invalid offsets after topic recreation)

**Verification:** Fresh test with `--max-comparisons 2` completed successfully:
- 2 LLM comparisons received and hydrated
- 1 `CJAssessmentCompletedV1` event received
- 1 `AssessmentResultV1` event received
- Runner completed in ~16 seconds (no timeout)
- Old batch events correctly filtered via `bos_batch_id` metadata

**Lesson Learned:** When Kafka topics are deleted/recreated, service consumer groups must be restarted to re-establish valid offsets—otherwise consumers silently fail to receive new messages.

---

### CJ Matching Strategy & Test Alignment (feature/cj-di-swappable-matching-strategy, PR-1 COMPLETE)

**Summary:** Reviewed the new DI-swappable PairMatchingStrategyProtocol wiring for the CJ
Assessment Service and aligned unit/integration tests with the OptimalGraphMatchingStrategy
wave semantics, while keeping tests focused on observable behavior (pair randomization,
comparison budgets, and metadata propagation).

**Key Changes:**
- Confirmed OptimalGraphMatchingStrategy is covered by a dedicated unit suite and kept
  that file as the canonical algorithm contract.
- Updated unit tests around pair_generation to:
  - Use the real strategy via a protocol-shaped wrapper where the behavior under test is
    wave selection and A/B position randomization.
  - Stub only the DB helpers (_fetch_assessment_context,_fetch_existing_comparison_ids,
    _fetch_comparison_counts) so tests exercise the real pairing logic without async
    SQLAlchemy complexity.
  - Relax and refocus the chi-squared randomization test to isolate _should_swap_positions
    from graph-matching details by using a simple deterministic test strategy.
- Updated comparison_processing tests to expect the new_load_essays_for_batch signature
  (now requires Settings to drive fairness-aware ordering via PAIR_GENERATION_SEED).
- For CJ integration tests that exercise request wiring and prompt construction
  (LLM payload construction, system prompt hierarchy, metadata persistence), replaced
  bare MagicMocks for PairMatchingStrategyProtocol with wrappers around the real
  OptimalGraphMatchingStrategy so they exercise actual matching behavior.
- Kept the DB-level randomization integration test focused on position randomization by
  using a deterministic anchor–student pairing strategy while still going through the
  real pair_generation and persistence layers.
- Updated the “full batch lifecycle with real database” test to reflect staged,
  wave-based submission:
  - Initial wave now submits 2 comparisons for 5 essays (floor(n/2)) instead of nC2=10.
  - Final assertions no longer assume a terminal COMPLETED state after a single callback
    simulation; instead they validate essay persistence, batch state presence, and that
    the LLM interaction layer was exercised at least once.

**Validation (PR‑1 COMPLETE):**
- `pdm run format-all`
- `pdm run lint-fix --unsafe-fixes`
- `pdm run pytest-root services/cj_assessment_service/tests/unit`
- `pdm run pytest-root services/cj_assessment_service/tests/integration`
- All 700 CJ unit + integration tests passing; existing typecheck-all remains clean.

---

## ➡️ Forward to next agent

### Priority 1: assignment_id Propagation Phase A (HIGH)
STATUS: COMPLETED (Phase A implemented on 2025-11-27)
Implement: `TASKS/assessment/propagate-assignment-id-from-bos-to-cj-request-phase-a.md`
1. Add `assignment_id` field to `BatchServiceCJAssessmentInitiateCommandDataV1`
2. BOS: pass `assignment_id` from `batch_metadata` to command
3. ELS: forward from command to dispatcher
4. ELS: populate `ELS_CJAssessmentRequestV1.assignment_id`

### Priority 2: assignment_id Propagation Phase B

Implement: `TASKS/assessment/propagate-assignment-id-from-cj-to-ras-storage-phase-b.md`

STATUS: COMPLETED (Phase B implemented on 2025-11-27)

1. Added `assignment_id` to `AssessmentResultV1` and wired CJ dual event publisher to populate it.

2. RAS: added `BatchResult.assignment_id` column + Alembic migration + TestContainers migration test.

3. RAS: handler and repository now persist `assignment_id`, and API read models expose it.
### Priority 3: CJ Assessment Hardening (3 Epics, 11 Stories)

**Epics created 2025-11-28:**
- EPIC-005: CJ Stability & Reliability (`docs/product/epics/cj-stability-and-reliability.md`)
- EPIC-006: Grade Projection Quality (`docs/product/epics/cj-grade-projection-quality.md`)
- EPIC-007: Developer Experience & Testing (`docs/product/epics/cj-developer-experience-and-testing.md`)

**PR Clusters:**

| PR | Stories | Focus |
|----|---------|-------|
| PR-1 | US-005.1, US-005.2, US-007.1 | Test harness & fixtures |
| PR-2 | US-005.1, US-005.2, US-005.4 | Stability semantics & completion safety |
| PR-3 | US-005.2, US-006.1, US-007.2 | BT SE & heuristic tidy-up |
| PR-4 | US-005.3 | Retry processor integration |
| PR-5 | US-006.3 | Confidence semantics |
| PR-6 | US-007.3 | Dev wrapper & examples |
| PR-7 | US-005.2, US-005.4 | Phase-2 resampling semantics & small-net guards |

**Active Tasks** (`TASKS/assessment/`):
- `us-0051-callback-driven-continuation-and-safe-completion-gating.md`
- `us-0052-score-stability-semantics-and-early-stopping.md`
- `us-0053-retry-semantics-and-end-of-batch-fairness.md`
- `us-0054-convergence-tests-for-iterative-bundled-mode.md`
- `us-0061-anchor-calibration-semantics-and-isotonic-constraints.md`
- `us-0062-robust-projection-with-missing-or-degenerate-anchors.md`
- `us-0063-confidence-semantics-for-grade-projections.md`
- `us-0071-matching-strategy-test-helpers-and-fairness-coverage.md`
- `us-0072-documentation-for-matching-budgets-and-stability-cadence.md`
- `us-0073-dev-runner-and-kafka-wrapper-for-cj-workflows.md`
- `us-0074-test-architecture-guardrails-and-strategy-extension-guide.md`

**2025-11-28 – PR-1 Harness Progress**
- Added shared matching-strategy helpers at
  `services/cj_assessment_service/tests/helpers/matching_strategies.py` with:
  - `make_real_matching_strategy_mock` delegating to `OptimalGraphMatchingStrategy`
    for `handle_odd_count`, `compute_wave_pairs`, and `compute_wave_size`.
  - `make_deterministic_anchor_student_strategy` providing deterministic
    anchor–student pairing for DB-level randomization tests.
- Updated CJ tests that depend on real wave semantics to use the helpers instead
  of ad-hoc `MagicMock(spec=PairMatchingStrategyProtocol)` wrappers:
  - Unit: `test_pair_generation_randomization.py`,
    `test_pair_generation_context.py`, `test_workflow_continuation.py`
  - Integration: `test_pair_generation_randomization_integration.py`,
    `test_llm_payload_construction_integration.py`,
    `test_system_prompt_hierarchy_integration.py`,
    `test_metadata_persistence_integration.py`,
    `test_real_database_integration.py`
- Verified `pdm run format-all`, `pdm run lint-fix --unsafe-fixes`,
  `pdm run typecheck-all`, and targeted CJ pytest nodes are all green.
  Core callback/stability semantics remain unchanged; this PR is focused on
  harness and fixture quality to unlock EPIC-005/EPIC-007 semantics work in
  subsequent PRs.

## Session Addendum (2025-11-28, PR-2 Semantics Draft)

- Implemented initial PR-2 semantics for zero-success / high-failure batches in
  `workflow_continuation.trigger_existing_workflow_continuation` and
  `batch_finalizer.BatchFinalizer`:
  - Added success-rate computation using `MIN_SUCCESS_RATE_THRESHOLD` and
    derived guards (`zero_successes`, `below_success_threshold`) that only
    engage once completion caps or budget are reached.
  - When caps are reached and success rate is too low (including zero
    successes), continuation now routes to `BatchFinalizer.finalize_failure`
    instead of `finalize_scoring`.
  - `finalize_failure` marks `CJBatchUpload.status` as `ERROR_PROCESSING`,
    sets `CJBatchState.state` to `FAILED`, annotates `processing_metadata`
    with a structured `failed_reason`, and publishes a thin
    `CJAssessmentFailedV1` event via the existing outbox publisher.
- Verified PR-2-oriented specs are executable as `xfail`:
  - `services/cj_assessment_service/tests/unit/test_workflow_continuation.py::test_high_failure_rate_does_not_finalize_with_zero_successes`
  - `services/cj_assessment_service/tests/integration/test_real_database_integration.py::TestRealDatabaseIntegration::test_all_failed_comparisons_move_batch_to_error_state`
  - Both remain `xfail` and run cleanly against the new semantics, confirming
    they are ahead of current behavior without destabilizing CI.

## Session Addendum (2025-11-29, PR-2 Implementation COMPLETE)

- Finalized and validated PR‑2 semantics for zero-success / low-success-rate batches:
  - `workflow_continuation.trigger_existing_workflow_continuation` now routes capped,
    low-success batches through `BatchFinalizer.finalize_failure` with a thin
    `CJAssessmentFailedV1` event instead of `finalize_scoring`.
  - `CJBatchUpload.expected_essay_count` is updated after anchors are hydrated so
    completion gating (n‑choose‑2 and `completion_denominator()`) reflects the full
    CJ graph (students + anchors), avoiding small-batch instability due to anchors
    being ignored in net size.
- Updated and un‑xfail’d PR‑2 guardrail tests:
  - Unit: zero-success and low-success-rate tests in
    `test_workflow_continuation.py` now assert `finalize_failure` vs
    `finalize_scoring` and pass against current semantics.
  - Integration: `test_all_failed_comparisons_move_batch_to_error_state` now passes
    with real repositories and asserts CJ batch status = ERROR_* and state = FAILED.
- Added forward-looking PR‑7 xfail specs:
  - Small‑net Phase‑2 resampling behaviour (including `resampling_pass_count` and
    small‑net caps) in `test_workflow_continuation.py`.
  - Convergence harness placeholders in `test_convergence_harness.py`.
- All CJ tests, format, lint, and `typecheck-all` are green on `main`; PR‑2 is
  implementation‑complete and merged. PR‑7 remains planned for Phase‑2 resampling
  semantics and convergence harness work.

## Session Addendum (2025-11-28, Phase-2 Comparisons Plan)

- Clarified Phase-2 comparison semantics in EPIC-005:
  - Phase 1: spend comparison budget on **unique coverage** of the n-choose-2
    essay graph (each unordered pair compared at least once, subject to caps).
  - Phase 2: once unique coverage is complete and stability has not passed,
    spend additional budget on **resampling the same graph** (re-judging
    existing pairs) until either:
      * Score stability threshold is reached (US-005.2), or
      * Global comparison budget / `MAX_ITERATIONS` is hit, with success-rate
        guards still enforced.
  - For small nets (e.g. < `MIN_RESAMPLING_NET_SIZE` essays), Phase-2
    resampling will be explicitly capped (e.g. `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`)
    to avoid tiny batches churning comparisons indefinitely when convergence
    cannot be reliably detected.
- Scheduled a dedicated PR for this work:
  - **PR-7: Phase-2 resampling semantics & small-net guards**, linked to
    US-005.2 and US-005.4. PR-2 remains focused on stability semantics,
    completion safety, and failure finalization; PR-5 remains scoped to
    confidence semantics (EPIC-006).
- Introduced an initial xfail unit spec for small-net Phase-2 behaviour:
  - `services/cj_assessment_service/tests/unit/test_workflow_continuation.py::test_small_net_phase2_requests_additional_comparisons_before_resampling_cap`
  - Encodes the expectation that once unique coverage is complete for a
    3-essay batch and stability has not passed, continuation requests at
    least one additional resampling wave before any Phase-2 small-net cap
    prevents further submissions.

**Archived:** `TASKS/archive/2025/11/assessment/cj-assessment-pr-review-improvements.md`

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

### NOT YET Validated (CJ/LPS Boundary, Tier-2 Limits)
- Rate limiting behavior under load using **Anthropic Tier 2** limits for Claude Sonnet 4.x  
  (current envelope: 10,000 RPM, 450k input tokens/min, 90k output tokens/min; was 50 RPM / 30k ITPM / 8k OTPM).
- Circuit breaker state transitions under real provider failures at Tier-2 throughput (open/half-open/closed behavior and recovery).
- Kafka consumer reconnection after broker failure (sustained callback ingestion while LPS is operating at higher Anthropic limits).
- LPS queue overflow scenarios under Tier-2 limits (queue depth, backpressure, and CJ retry behavior), with updated metrics/alerts reflecting the new capacity.

---

## ✅ RECENTLY COMPLETED (Reference Only)

- **2025-11-27 assignment_id Propagation Phase A & B COMPLETE**  
  - Phase A: Client → BOS → ELS → CJ now threads `assignment_id` via `ClientBatchPipelineRequestV1.prompt_payload.assignment_id`, `BatchServiceCJAssessmentInitiateCommandDataV1.assignment_id`, and `ELS_CJAssessmentRequestV1.assignment_id`.  
  - Phase B: CJ → RAS path extended so `AssessmentResultV1.assignment_id` is populated by the dual event publisher, RAS persists it on `BatchResult.assignment_id` via Alembic migration `0a6c563e4523_add_assignment_id_to_batch_results`, and `BatchStatusResponse` exposes `assignment_id` for downstream consumers.  
  - Functional test `test_complete_cj_assessment_processing_pipeline` now asserts the full client → BOS → ELS → CJ → RAS round-trip of `assignment_id` using RAS’ `/internal/v1/batches/{batch_id}/status` API (RAS is the source of truth for ENG5/guest flows).

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
