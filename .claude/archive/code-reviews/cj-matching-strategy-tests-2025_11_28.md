---
title: "CJ Matching Strategy & Test Design Review"
date: 2025-11-28
review_target: "feature/cj-di-swappable-matching-strategy"
scope:
  - services/cj_assessment_service/cj_core_logic/matching_strategies/optimal_graph_matching.py
  - services/cj_assessment_service/cj_core_logic/pair_generation.py
  - services/cj_assessment_service/cj_core_logic/comparison_processing.py
  - services/cj_assessment_service/tests/unit/test_optimal_graph_matching.py
  - services/cj_assessment_service/tests/unit/test_pair_generation_randomization.py
  - services/cj_assessment_service/tests/unit/test_pair_generation_context.py
  - services/cj_assessment_service/tests/unit/test_comparison_processing.py
  - services/cj_assessment_service/tests/integration/test_pair_generation_randomization_integration.py
  - services/cj_assessment_service/tests/integration/test_llm_payload_construction_integration.py
  - services/cj_assessment_service/tests/integration/test_metadata_persistence_integration.py
  - services/cj_assessment_service/tests/integration/test_real_database_integration.py
summary: |
  Reviewed the DI-swappable PairMatchingStrategyProtocol integration and aligned
  unit/integration tests with the new OptimalGraphMatchingStrategy-based wave
  semantics, while keeping tests focused on behavior (pair randomization,
  request wiring, and metadata persistence) rather than implementation details.

notes:
  - Confirmed that OptimalGraphMatchingStrategy is type-safe and covered by a
    dedicated unit suite (test_optimal_graph_matching.py).
  - Identified that several tests still treated pair generation as nC2 over all
    essays; this conflicts with the new "each essay at most once per wave"
    design and COMPARISONS_PER_STABILITY_CHECK_ITERATION-based budget semantics.
  - Found multiple MagicMock-based PairMatchingStrategyProtocol fixtures that
    were unconfigured; after wiring the protocol into pair_generation, these
    mocks produced empty iterables / ValueErrors or coroutine-type errors.
  - Verified that the CJ Assessment service contract (020.7) and testing rules
    (070/075) encourage mocking external boundaries but allow real algorithm
    implementations in tests when they are the subject under test.

changes_made:
  - Switched unit pair-generation tests to use OptimalGraphMatchingStrategy via
    a protocol-shaped wrapper, stubbing only database access helpers.
  - Updated randomization tests:
      * Determinism: now asserts that waves generated with the same seed and
        strategy configuration produce identical pair orderings.
      * Swap behavior: compares baseline vs "swap first" runs to prove that
        _should_swap_positions actually inverts the first pair.
      * Fairness: uses a simple deterministic pairing strategy inside the test
        when running the chi-squared check so the statistic measures position
        randomization, not graph matching quirks.
  - Adjusted threshold/cap tests in test_pair_generation_context to align with
    wave-based semantics (floor(n/2) per wave) while still respecting the
    global MAX_PAIRWISE_COMPARISONS cap.
  - Updated comparison_processing tests to expect the new_load_essays_for_batch
    signature, which now requires Settings for seed-based fairness ordering.
  - For integration tests that care about end-to-end prompts and metadata
    (LLM payload construction, system prompt hierarchy, metadata persistence),
    replaced bare MagicMocks with protocol-shaped wrappers around the real
    OptimalGraphMatchingStrategy so they exercise the actual matching behavior.
  - For the DB-level pair randomization integration test, kept a focused,
    deterministic PairMatchingStrategy stub that always produces anchor–student
    pairs; this isolates A/B position randomization from graph matching while
    still using the real pair_generation pipeline and persistence layer.
  - Updated the "full batch lifecycle with real database" integration test to
    reflect staged, wave-based submission:
      * Initial wave now submits 2 comparisons for 5 essays instead of nC2=10.
      * Final assertion no longer assumes the batch reaches a terminal COMPLETED
        state after a single callback simulation cycle, but still verifies that
        essays and batch state are persisted correctly and that the LLM
        interaction layer is exercised.

status:
  unit_tests: "services/cj_assessment_service/tests/unit - all passing"
  integration_tests: "services/cj_assessment_service/tests/integration - all passing"
  typecheck_all: "pdm run typecheck-all (unchanged, still clean)"

open_questions:
  - When iterative, stability-driven batching (LLM_BATCHING_MODE != PER_REQUEST)
    is fully wired, we should revisit the "full batch lifecycle" test to assert
    explicit completion criteria (stability vs max comparisons) across multiple
    waves instead of inferring behaviour from a single simulated iteration.
  - Once COMPARISONS_PER_STABILITY_CHECK_ITERATION is the canonical wave-size
    control in production, we may want an additional contract-style test that
    asserts the orchestrator and pair_generation honour that setting in both
    initial submission and continuation flows.
