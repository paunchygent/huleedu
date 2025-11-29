# CJ Assessment Service Tests – Matching Strategy & Stability Notes

This file documents how tests in `services/cj_assessment_service/tests/` should
interact with the pair-matching layer and stability logic. It is intended to
keep unit, integration, and convergence tests aligned with the service
architecture and Rules 070 / 075.

## 1. Matching Strategy vs Orchestration

- **Matching strategy (`PairMatchingStrategyProtocol`)**
  - Responsibility: given a set of essays, existing pairs, and comparison counts,
    propose a *wave* of new pairs that maximizes information gain.
  - Default implementation: `OptimalGraphMatchingStrategy` (Blossom-based
    maximum-weight matching).
  - Behavior:
    - After odd-count handling, each wave contains at most `n_essays // 2`
      pairs (perfect matching).
    - Uses comparison counts (fairness) and BT proximity as weighting terms.
    - `compute_wave_size(n)` returns this theoretical maximum, not a hard cap.

- **Orchestration / continuation**
  - Responsibility: decide *how many waves* to run and *when to stop* based on
    stability, success rate, and global budgets.
  - Governed by:
    - `MAX_PAIRWISE_COMPARISONS` (hard global cap)
    - `MIN_COMPARISONS_FOR_STABILITY_CHECK`
    - `COMPARISONS_PER_STABILITY_CHECK_ITERATION` (stability cadence hint)
    - `SCORE_STABILITY_THRESHOLD`, `TARGET_MEAN_SE`
    - `MIN_SUCCESS_RATE_THRESHOLD`, `MAX_ITERATIONS`

**Rule for tests:**  
Do not push orchestration concerns (budgets, stability, retries) into matching
strategy tests. Keep strategy tests about *which pairs are chosen*, and
orchestration tests about *when more pairs are requested* or *when we stop*.

## 2. When to Use the Real Strategy vs Deterministic Stubs

### 2.1. Use the real `OptimalGraphMatchingStrategy` when…

- **Unit-testing the strategy itself**
  - File pattern: `test_optimal_graph_matching.py`.
  - No mocks: test invariants (no self-pairs, each essay appears at most once
    per wave, existing pairs excluded, tie-breaking determinism, fairness and
    BT weighting) directly against the real implementation.

- **Unit-testing pair generation behavior**
  - Files: `test_pair_generation_randomization.py`,
    `test_pair_generation_context.py`, and similar.
  - Pattern:
    - Use a protocol-shaped wrapper that delegates to a real
      `OptimalGraphMatchingStrategy` for `handle_odd_count`, `compute_wave_pairs`,
      and `compute_wave_size`.
    - Stub **only** database access helpers:
      - `_fetch_assessment_context`
      - `_fetch_existing_comparison_ids`
      - `_fetch_comparison_counts`
    - Tests should assert things like:
      - Deterministic wave composition under a fixed seed.
      - Interaction with global cap (`MAX_PAIRWISE_COMPARISONS`).
      - Correct construction of `ComparisonTask` (prompts, blocks, metadata).

- **Integration tests about prompts / metadata / end-to-end flows**
  - Files: e.g. `test_llm_payload_construction_integration.py`,
    `test_system_prompt_hierarchy_integration.py`,
    `test_metadata_persistence_integration.py`,
    `test_real_database_integration.py`.
  - Pattern:
    - Use a protocol-shaped mock that delegates to a real
      `OptimalGraphMatchingStrategy` (strategy behavior is “real”).
    - Keep **external boundaries** mocked (LLM HTTP, Kafka, Content Service) as
      per Rules 070 / 075.
    - The purpose is to test:
      - That `ComparisonTask` flows through to LLM payloads correctly.
      - That metadata, original request, and continuation wiring are correct.
      - That DB-level state reflects realistic waves, not synthetic ones.

### 2.2. Use deterministic stub strategies when…

- **You are isolating A/B position randomization or a very specific layout**
  - Example: `test_pair_generation_randomization_integration.py` (DB-level
    anchor vs student position fairness).
  - Pattern:
    - Implement a small `PairMatchingStrategyProtocol` stub *in the test* that:
      - Returns all essays untouched from `handle_odd_count`.
      - Produces a deterministic set of pairs (e.g. anchor–student pairs) from
        `compute_wave_pairs`, filtered by `existing_pairs`.
      - Implements `compute_wave_size` consistently with the stubbed behavior.
    - This keeps pair *selection* deterministic so the test can focus on
      per-pair position randomization (`_should_swap_positions`) or DB
      persistence of A/B positions.

**Rule for tests:**  
If your assertion fundamentally depends on *how* pairs are selected (fairness,
coverage, graph structure), use the real strategy. Only stub the strategy when
the test is exercising *something else* (e.g. position randomization, callback
flow) and a simpler pairing pattern improves clarity.

## 3. What NOT to Do with Matching Strategy Mocks

- **Avoid bare MagicMocks for strategy when pairs are consumed**
  - Do **not** use a raw `MagicMock(spec=PairMatchingStrategyProtocol)` with
    no configured behavior in tests that iterate over returned pairs. This
    leads to:
    - Empty iterators → “not enough values to unpack” errors.
    - Coroutine-type errors when AsyncMocks leak into synchronous paths.
  - Either:
    - Delegate to a real implementation; or
    - Provide a simple deterministic stub with explicit semantics.

- **Do not push budget logic into `compute_wave_size`**
  - `compute_wave_size(n)` should remain strategy-driven (e.g. `n // 2` for a
    perfect matching) and used for logging/metrics.
  - Per-iteration budgets and stability cadence belong in the orchestration
    layer; tests should treat `COMPARISONS_PER_STABILITY_CHECK_ITERATION` as a
    *hint* for when stability is reevaluated, not a hard per-wave cap.

## 4. Fairness Counts and Error Handling (Alignment with PR 4)

- Comparison counts used for fairness in matching should represent
  **successful** comparisons only:
  - `_fetch_comparison_counts` should exclude error winners / failed
    comparisons when counting how often an essay has been compared.
  - Failed comparisons may still exist in the DB for observability, but
    should not inflate fairness counts.
- Tests that cover fairness behavior (e.g. “prefer less-compared essays”) must
  set up comparison-pair fixtures accordingly:
  - Successful comparisons contribute to counts.
  - Error/failed comparisons are either filtered out or counted separately,
    depending on the scenario being tested.

## 5. Stability & Success-Rate Logic (Alignment with PR 1 & PR 2)

- Stability tests should be written at the **continuation/orchestration** level
  (e.g. `workflow_continuation.trigger_existing_workflow_continuation`), not
  inside matching tests.
- Stability criteria should cover:
  - `callbacks_received >= MIN_COMPARISONS_FOR_STABILITY_CHECK`
  - `max_score_change <= SCORE_STABILITY_THRESHOLD`
  - `mean_bt_se <= TARGET_MEAN_SE`
  - `success_rate >= MIN_SUCCESS_RATE_THRESHOLD`
  - Where appropriate, relationship to `COMPARISONS_PER_STABILITY_CHECK_ITERATION`
    (e.g. “re-check stability only after we’ve accumulated at least this many
    new comparisons since the last check”).
- Retry integration tests (PR 2) should:
  - Use realistic matching behavior where success-rate and failure patterns
    matter.
  - Keep retry decisions (and low-success-rate guards) in continuation tests,
    not in strategy unit tests.

---

**TL;DR for authors**

- Use the **real matching strategy** by default, especially when testing waves,
  fairness, or pipelines.
- Use **deterministic stub strategies** only when testing something that is
  independent of the algorithm’s pairing decisions (e.g., A/B position
  randomization or callback plumbing).
- Treat `COMPARISONS_PER_STABILITY_CHECK_ITERATION` as a stability cadence
  hint, not a per-wave size; reserve hard caps for `MAX_PAIRWISE_COMPARISONS`.
