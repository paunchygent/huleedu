---
id: 'us-0051-callback-driven-continuation-and-safe-completion-gating'
title: 'US-005.1: Callback-driven continuation and safe completion gating'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-28'
last_updated: '2025-12-06'
related: ['EPIC-005', 'pr-7-phase-2-resampling-and-convergence-harness', 'llm-mock-provider-cj-behavioural-parity-tests']
labels: ['docker', 'integration-tests', 'small-net', 'eng5', 'llm-provider']
---
# US-005.1: Callback-driven continuation and safe completion gating

## Objective

Ensure the CJ workflow only proceeds when all expected callbacks have arrived, preventing premature finalization with incomplete comparison data.

## Context

Part of EPIC-005 (CJ Stability & Reliability). The current implementation may finalize batches prematurely when callback counts are miscalculated or when high failure rates inflate the received count without sufficient valid comparisons.

## Acceptance Criteria

- [ ] `check_workflow_continuation` returns `true` only when:
  - `submitted_comparisons > 0`, and
  - `pending_callbacks == 0` (where `pending = submitted - (completed + failed)`),
  - Logs all four counters plus `completion_denominator` for the batch
- [ ] When `pending_callbacks > 0`, continuation is skipped and a structured log line shows `pending_callbacks`, `submitted_comparisons`, `completed_comparisons`, and `failed_comparisons`
- [ ] `CJBatchState.completion_denominator()` is the single source of truth for completion math in both `BatchCompletionChecker` and `BatchCompletionPolicy`:
  - For small batches (e.g. 4 essays → 6 max pairs), completion is measured against the n-choose-2 maximum
  - For large batches, completion is measured against `min(total_budget, max_possible_pairs)`
- [ ] A batch with `completed_comparisons == 0` is **never** finalized as COMPLETE_*:
  - If all attempts fail, the batch ends in an explicit error status and logs a clear error reason
- [ ] Integration tests cover:
  - 2‑essay batch (minimum viable)
  - 100+ essay batch (scalability) with realistic budgets
  - ≥50% callback failures, verifying that the batch is not incorrectly marked complete

## Implementation Notes

Suggested task doc path: `TASKS/assessment/cj-stab-1-callback-continuation-and-completion.md`

Key files to modify:
- `services/cj_assessment_service/src/workflow_continuation.py`
- `services/cj_assessment_service/src/batch_completion_checker.py`
- `services/cj_assessment_service/src/batch_completion_policy.py`
- `services/cj_assessment_service/src/models/cj_batch_state.py`

## Related

- Parent epic: [EPIC-005: CJ Stability & Reliability](../../../docs/product/epics/cj-stability-and-reliability.md)
- Related story: US-005.2 (Score stability semantics)

## Progress (PR-2 snapshot)

- PR-2 implements callback gating, stability checks, and success-rate based failure semantics in the CJ Assessment Service.
- Guardrail tests for zero-success and low-success-rate batches now assert failure finalization (`finalize_failure`) and are passing.
- Integration coverage has been added for small (2-essay) and larger batches to ensure `completion_denominator()` and pending callback logic behave correctly.
- Phase-2 resampling and small-net caps remain out of scope for PR-2 and will be delivered in PR-7.

## Next: Docker-backed small-net continuation validation (ENG5 LOWER5)

Goal: Add a docker-backed, "completed-successful small net" test that validates callback-driven continuation semantics end-to-end (AGW → BOS/BCS/ELS → CJ → LPS mock → CJ/RAS), with a focus on small-net coverage and continuation behaviour under the ENG5 LOWER5 mock profile.

This section defines the concrete implementation checklist for `tests/integration/test_cj_small_net_continuation_docker.py`. The test will be cross-linked with:

- EPIC-005 (CJ Stability & Reliability)
- PR-7 (Phase-2 resampling and convergence harness)
- `TASKS/infrastructure/llm-mock-provider-cj-behavioural-parity-tests.md` (LPS mock profile parity)

### Test 1: `test_cj_small_net_continuation_metadata_completed_successful`

Validated behaviour: A LOWER5 small-net batch (ENG5) reaches a completed-successful state; `CJBatchState` counters and `processing_metadata` are consistent with all callbacks arriving and with small-net coverage semantics.

- [x] **Environment & gating**
  - [x] Use `ServiceTestManager.get_validated_endpoints()` and ensure:
    - [x] `"llm_provider_service"` is healthy.
    - [x] `"cj_assessment_service"` is healthy.
    - [x] `"api_gateway_service"` is healthy.
  - [x] Call `GET /admin/mock-mode` on `llm_provider_service` and:
    - [x] Skip when status != 200.
    - [x] Skip when `use_mock_llm` is not `true`.
    - [x] Skip when `mock_mode != "eng5_lower5_gpt51_low"`.

- [x] **Batch creation via AGW**
  - [x] Use `ServiceTestManager.create_batch_via_agw(...)` to create an ENG5 batch with:
    - [x] `expected_essay_count=5` (small net).
    - [x] `course_code=ENG5` (or `"ENG5"`), with any additional flags needed so CJ runs.
  - [x] Capture `batch_id` and `correlation_id` for later inspection.

- [x] **Wait for final CJ state**
  - [x] Poll for `CJBatchState` or CJ status (via HTTP or DB helper) with a hard timeout ≤ 60s.
  - [x] Assert:
    - [x] The batch reaches a final state (no timeout).
    - [x] Final state is a success state (e.g. `CJBatchStateEnum.COMPLETED`), not a failure/cancelled state.

- [x] **Counters and completion invariants**
  - [x] Read from `CJBatchState`:
    - [x] `submitted_comparisons`, `completed_comparisons`, `failed_comparisons`.
    - [x] `total_comparisons`, `total_budget`, `current_iteration`.
  - [x] Compute:
    - [x] `callbacks_received = completed_comparisons + failed_comparisons`.
    - [x] `denominator = batch_state.completion_denominator()`.
  - [x] Assert:
    - [x] `failed_comparisons == 0`.
    - [x] `callbacks_received > 0`.
    - [x] `callbacks_received == denominator` (PR‑2 completion invariant).
    - [x] `total_comparisons == submitted_comparisons == completed_comparisons`.
    - [x] `total_comparisons <= total_budget`.

- [x] **Coverage and small-net metadata**
  - [x] Extract `metadata = batch_state.processing_metadata` as `dict`.
  - [x] Assert presence and types:
    - [x] `max_possible_pairs` (`int`).
    - [x] `successful_pairs_count` (`int`).
    - [x] `unique_coverage_complete` (`bool`).
    - [x] `resampling_pass_count` (`int`).
  - [x] For LOWER5 (5-essay small net) assert:
    - [x] `max_possible_pairs == 10` (C(5,2)).
    - [x] `successful_pairs_count == 10`.
    - [x] `unique_coverage_complete is True`.
    - [x] `resampling_pass_count >= 0` (and optionally ≤ configured cap).

- [x] **BT quality metadata (shape, not exact values)**
  - [x] From `metadata`, read:
    - [x] `bt_se_summary` (dict).
    - [x] `bt_quality_flags` (dict).
  - [x] Assert:
    - [x] `bt_se_summary` has keys `mean_se`, `max_se`, `mean_comparisons_per_item`, `isolated_items` with numeric types.
    - [x] `bt_quality_flags` has boolean keys `bt_se_inflated`, `comparison_coverage_sparse`, `has_isolated_items`.

- [x] **Decision-module consistency (inferred)**
  - [x] Compute:
    - [x] `success_rate = completed_comparisons / callbacks_received`.
    - [x] `callbacks_reached_cap = callbacks_received >= denominator`.
    - [x] `pairs_remaining = total_budget - submitted_comparisons`, `budget_exhausted = pairs_remaining <= 0`.
  - [x] Assert:
    - [x] `success_rate` is effectively `1.0` (or within tight tolerance).
    - [x] At least one of `callbacks_reached_cap`, `budget_exhausted`, or (if encoded in metadata) `small_net_cap_reached` is `True`.
    - [x] There is no failure marker in state/metadata (consistent with `ContinuationDecision.FINALIZE_SCORING`).

### Test 2: `test_cj_small_net_continuation_requests_more_before_completion`

Validated behaviour: There exists at least one realistic small-net scenario (ENG5 LOWER5 profile active) where CJ **requests more comparisons** before eventually finalizing – i.e. the real system exercises `REQUEST_MORE_COMPARISONS` on the path to completion.

- [ ] **Environment & gating (same as Test 1)**
  - [ ] Use `ServiceTestManager` to validate endpoints.
  - [ ] Gate on `/admin/mock-mode` for `use_mock_llm=true` and `mock_mode="eng5_lower5_gpt51_low"`.

- [ ] **Batch creation encouraging "request more"**
  - [ ] Create a 5-essay ENG5 batch via `create_batch_via_agw(...)` as above.
  - [ ] Ensure configuration or environment for this test is such that:
    - [ ] First iteration cannot satisfy stability or completion conditions alone (e.g. higher `MIN_COMPARISONS_FOR_STABILITY_CHECK`, or a budget that allows multiple iterations).

- [ ] **Observe intermediate vs final comparison counts**
  - [ ] Optionally, snapshot an early state (pre-final) where:
    - [ ] `submitted_comparisons` equals the initial small-net wave (≈10), and batch is not yet complete.
  - [ ] Poll for final success state (≤ 60s) as in Test 1.
  - [ ] On final state, read:
    - [ ] `submitted_comparisons_final`, `total_comparisons_final`, `completed_comparisons_final`, `failed_comparisons_final`.
  - [ ] Assert:
    - [ ] `failed_comparisons_final == 0`.
    - [ ] `submitted_comparisons_final` and/or `total_comparisons_final` are **greater** than the initial expected small-net count (e.g. `> 10`), proving that extra comparisons were requested.
    - [ ] `completed_comparisons_final == total_comparisons_final` (no pending work at completion).

- [ ] **Final metadata and small-net flags**
  - [ ] Inspect `processing_metadata` at final state and assert:
    - [ ] `max_possible_pairs == 10`.
    - [ ] `successful_pairs_count == 10`.
    - [ ] `unique_coverage_complete is True`.
    - [ ] `resampling_pass_count >= 1` (or at least > 0) to confirm that small-net coverage/resampling semantics were exercised.

- [ ] **Final decision consistency**
  - [ ] Recompute decision invariants as in Test 1:
    - [ ] `callbacks_received_final == completion_denominator_final`.
    - [ ] `success_rate_final` high (≈1.0).
  - [ ] Assert:
    - [ ] Final state is success (consistent with `ContinuationDecision.FINALIZE_SCORING`).
    - [ ] Combined with the increased comparison counts, this demonstrates a real `REQUEST_MORE_COMPARISONS → FINALIZE_SCORING` path under docker.

> Implementation note: if the docker environment cannot reliably produce an intermediate "request more" iteration without intrusive configuration, this second test can initially be marked `xfail` with a clear reason, or deferred to a follow-up once the continuation cadence is fully parameterized for test runs.
