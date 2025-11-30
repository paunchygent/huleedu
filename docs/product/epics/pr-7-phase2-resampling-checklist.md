---
id: "pr-7-phase2-resampling-checklist"
type: "implementation-checklist"
status: "draft"
created: 2025-11-30
last_updated: 2025-11-30
scope: "backend"
parent_epic: "cj-stability-and-reliability-epic"
---

# PR‑7: Phase‑2 Resampling & Convergence Harness – Implementation Checklist

This checklist scopes the work for PR‑7 under EPIC‑005 (CJ Stability & Reliability).
It assumes PR‑2 (continuation + stability semantics) and PR‑4 (BT scoring refactor)
are already merged and stable.

## 1. Orientation & Baseline

- [ ] Read:
  - [ ] `docs/product/epics/cj-stability-and-reliability-epic.md` (PR‑7 section)
  - [ ] `services/cj_assessment_service/cj_core_logic/workflow_continuation.py`
  - [ ] `services/cj_assessment_service/cj_core_logic/pair_generation.py`
  - [ ] `services/cj_assessment_service/cj_core_logic/scoring_ranking.py`
  - [ ] `services/cj_assessment_service/models_db.py` (`CJBatchState`)
- [ ] Establish a green baseline:
  - [ ] `pdm run pytest-root services/cj_assessment_service/tests`

## 2. Coverage Metrics & Batch Metadata

**Goal:** make Phase‑2 decisions from real coverage data, not only `expected_essay_count`.

- [ ] Extend `CJComparisonRepositoryProtocol` with a helper for coverage metrics, e.g.:
  - [ ] `get_successful_pairs_metrics(cj_batch_id) -> {max_possible_pairs, successful_pairs_count}`
  - [ ] Implement in the concrete comparison repository.
- [ ] Decide how to use coverage for completion vs metadata:
  - [ ] Keep `CJBatchState._max_possible_comparisons()` based on `expected_essay_count` for
        `completion_denominator()` (unchanged semantics), and
  - [ ] Treat coverage metrics in `processing_metadata` as the authoritative view for Phase‑2.
    - (Optional) If updating `_max_possible_comparisons()`, do it via existing metadata without adding DB calls inside the method.
- [ ] In `trigger_existing_workflow_continuation`:
  - [ ] After BT scoring and before finalization, fetch coverage metrics via the new repository helper.
  - [ ] Compute:
    - [ ] `max_possible_pairs`
    - [ ] `successful_pairs_count`
    - [ ] `unique_coverage_complete = successful_pairs_count >= max_possible_pairs` (when `max_possible_pairs > 0`)
    - [ ] Initialise `resampling_pass_count` to `0` when absent.
  - [ ] Persist these values into `CJBatchState.processing_metadata` via `merge_batch_processing_metadata`.
- [ ] Add / extend a unit test that asserts the metadata keys are present after a continuation iteration.

## 3. Small‑Net Phase‑2 Semantics in `workflow_continuation`

**Goal:** implement explicit Phase‑2 resampling behaviour for small nets while keeping
PR‑2/PR‑4 semantics unchanged for large nets.

### 3.1 Settings

- [ ] Add new CJ Assessment `Settings` fields:
  - [ ] `MIN_RESAMPLING_NET_SIZE: int = 10`
  - [ ] `MAX_RESAMPLING_PASSES_FOR_SMALL_NET: int = 2`
- [ ] Document them (docstrings + runbook notes).

### 3.2 Branching Logic

In `trigger_existing_workflow_continuation`:

- [ ] Determine whether the batch is a small net:
  - [ ] `expected = batch_state.batch_upload.expected_essay_count or 0`
  - [ ] `is_small_net = expected < settings.MIN_RESAMPLING_NET_SIZE`
- [ ] For **large nets** (`not is_small_net`):
  - [ ] Preserve existing PR‑2 semantics exactly (no behaviour changes).
- [ ] For **small nets**:
  - [ ] When callbacks for the current iteration reach `completion_denominator()` and stability
        has **not** passed:
    - [ ] If `unique_coverage_complete` is `False` and coverage metrics show all pairs seen:
      - [ ] Set `unique_coverage_complete=True` and `resampling_pass_count=0` in metadata.
    - [ ] If `unique_coverage_complete is True` and:
      - [ ] Budget remains, and
      - [ ] `resampling_pass_count < MAX_RESAMPLING_PASSES_FOR_SMALL_NET`:
        - [ ] Call `request_additional_comparisons_for_batch` in resampling mode
              (see Section 4).
        - [ ] Increment and persist `resampling_pass_count`.
        - [ ] **Do not** finalize yet.
    - [ ] Otherwise (Phase‑2 cap reached or no budget):
      - [ ] Proceed to finalization using the existing stability + success‑rate gates.
- [ ] Add targeted logging:
  - [ ] `small_net_phase2_entered` when moving into Phase‑2 for a batch.
  - [ ] `small_net_resampling_wave_started` each time a resampling wave is triggered.

### 3.3 Tests to Flip from xfail

In `services/cj_assessment_service/tests/unit/test_workflow_continuation.py`:

- [ ] Make these tests pass (remove/adjust `xfail` once semantics are in place):
  - [ ] `test_small_net_phase2_requests_additional_comparisons_before_resampling_cap`
    - Should see `request_additional_comparisons_for_batch` called for a 3‑essay net with
      full coverage and remaining budget; no immediate finalization.
  - [ ] `test_small_net_resampling_respects_resampling_pass_cap`
    - Should see no resampling when `resampling_pass_count` equals the cap and finalization occurs instead.

## 4. Pair Generation – Resampling Mode

**Goal:** let pair generation support both coverage and resampling phases without owning workflow logic.

- [ ] Extend pair generation API in `pair_generation.py` to accept a mode hint, e.g.:
  - [ ] `mode: PairGenerationMode = PairGenerationMode.COVERAGE`
- [ ] Implement mode handling:
  - [ ] `COVERAGE`: retain current behaviour (new pairs until coverage or cap).
  - [ ] `RESAMPLING`:
    - [ ] Build new comparison tasks only from the existing comparison graph for the batch.
    - [ ] Do not introduce new essay nodes.
    - [ ] Use simple fairness heuristics so retry/resampling waves do not systematically over‑sample already heavily compared essays.
- [ ] Wire `request_additional_comparisons_for_batch` (and any helpers it uses) to pass the mode
      based on `unique_coverage_complete` and small‑net settings.
- [ ] Extend / add tests in `services/cj_assessment_service/tests/unit/test_pair_generation_context.py`:
  - [ ] Confirm resampling mode never creates pairs involving unseen essays.
  - [ ] Validate basic fairness properties (e.g., no extreme over-sampling of a single essay).

## 5. Convergence Harness (US‑005.4)

**Goal:** implement a convergence harness over synthetic nets and replace the xfail specs
in `test_convergence_harness.py` with working tests.

- [ ] Add a new harness module (proposed):
  - [ ] `services/cj_assessment_service/cj_core_logic/convergence_harness.py`
- [ ] Harness responsibilities:
  - [ ] Accept configuration:
    - `COMPARISONS_PER_STABILITY_CHECK_ITERATION`
    - `MIN_COMPARISONS_FOR_STABILITY_CHECK`
    - `MAX_ITERATIONS`
    - `MAX_PAIRWISE_COMPARISONS`
  - [ ] Simulate:
    - [ ] Phase‑1 (coverage): waves add new edges until coverage or cap.
    - [ ] Phase‑2 (resampling): waves reuse the same n‑choose‑2 graph until stability or caps.
  - [ ] Drive the real BT scoring + stability helpers:
    - [ ] `record_comparisons_and_update_scores(...)`
    - [ ] `check_score_stability(...)`
  - [ ] Produce a `HarnessResult` capturing:
    - [ ] Final BT scores.
    - [ ] Whether stability was achieved.
    - [ ] Which cap fired: `stability`, `iterations`, or `budget`.
- [ ] Replace xfail specs in `services/cj_assessment_service/tests/unit/test_convergence_harness.py`:
  - [ ] `test_convergence_harness_stops_on_stability_before_max_iterations`
    - Uses an easy synthetic net where stability is achieved early.
  - [ ] `test_convergence_harness_stops_after_max_iterations_or_budget`
    - Uses a difficult net where the harness must stop on caps, not stability.

## 6. Non‑Regression & Docs

- [ ] Re‑run CJ Assessment tests:
  - [ ] `pdm run pytest-root services/cj_assessment_service/tests`
- [ ] Verify PR‑2/PR‑4 semantics for large nets remain unchanged (no regressions in existing
      workflow continuation and scoring integration tests).
- [ ] Update documentation:
  - [ ] `docs/product/epics/cj-stability-and-reliability-epic.md`:
    - [ ] Mark PR‑7 items implemented and align narrative with the final behaviour.
  - [ ] `docs/operations/cj-assessment-runbook.md`:
    - [ ] Document small‑net behaviour and the two‑phase model (coverage + resampling).
    - [ ] Describe new settings:
      - `MIN_RESAMPLING_NET_SIZE`
      - `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`
    - [ ] Explain coverage metadata on `CJBatchState.processing_metadata`:
      - `max_possible_pairs`
      - `successful_pairs_count`
      - `unique_coverage_complete`
      - `resampling_pass_count`
- [ ] Final quality gates from repo root:
  - [ ] `pdm run format-all`
  - [ ] `pdm run lint-fix --unsafe-fixes`
  - [ ] `pdm run typecheck-all`
