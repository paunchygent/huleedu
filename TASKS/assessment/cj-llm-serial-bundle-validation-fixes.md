---
id: cj-llm-serial-bundle-validation-fixes
title: Cj Llm Serial Bundle Validation Fixes
type: task
status: in_progress
priority: high
domain: assessment
owner_team: agents
created: '2025-11-19'
last_updated: '2025-12-10'
service: cj_assessment_service
owner: ''
program: ''
related: ['EPIC-005', 'EPIC-008', 'EPIC-011']
labels: []
---

# TASK-CJ-LLM-SERIAL-BUNDLE-VALIDATION-FIXES – CJ Batch State, Fairness & Provider Diagnostics

**Scope:**  
- Correctness and observability issues discovered during ENG5 serial-bundle validation runs.  
- Services: **CJ Assessment Service** (batch state, pair generation, callbacks) and **LLM Provider Service** (queue hygiene, provider diagnostics).

**Background:**  
- `per_request` baseline: 4/4 comparisons, stable BT + projections.  
- `serial_bundle` batch 33: 100 pairs → 66 Anthropic errors, degenerate BT scores, completion logs >100%.  
- `serial_bundle` batch 34: 10/10 success, but one stray callback correlation ID and evidence of orphan callbacks / stuck queue items.

**Problem Areas (from investigation docs):**  
1. Batch completion semantics and metrics divergence from DB reality.  
2. Pair generation position bias (anchors overrepresented as `essay_a`).  
3. Poorly classified Anthropic provider errors during serial_bundle runs (rate limits vs server errors vs overload).  
4. Queue hygiene issues: stuck `PROCESSING` items and orphan callbacks.

**This task decomposes the above into PRs:**  
- **PR 1 – CJ Batch Completion & Metrics Semantics Fix**  
- **PR 2 – Pair Generation Fairness & Anchor Position Balancing**  
- **PR 3 – Anthropic Error Diagnostics for Serial-Bundle ENG5 Runs**  
- **PR 4 – Queue Hygiene & Orphan Callback Handling**

**Success Criteria:**
- Serial-bundle runs never report >100% completion and match DB counts.
- A/B positions are balanced for anchors and students across runs.
- Anthropic failures are classified with structured `ErrorDetail` + Prometheus metrics by `error_type`.
- Stuck queue items and orphan callbacks are surfaced via metrics/logs and cleaned up deterministically.

**Progress 2025-11-21:**
- PR1: stability-first completion shipped (callback-driven scoring, nC₂ denominator cap, monitor recovery-only). Unit tests added; targeted pytest command below.
- PR3: Anthropic client hardened (429 Retry-After, 529/overloaded retryable, stop_reason=max_tokens, prompt caching hook + metadata). Integration test still to extend for 529/stop_reason cases.
- Docs updated: CJ README (completion path) and LPS README (Anthropic ops/caching). Tests run: `pdm run pytest-root services/cj_assessment_service/tests/unit/test_workflow_continuation.py services/cj_assessment_service/tests/unit/test_completion_threshold.py services/llm_provider_service/tests/integration/test_anthropic_error_diagnostics.py`.

**Progress 2025-12-07 / 2025-12-08 (this session):**
- PR1 – Completion safety & callback semantics:
  - `BatchCompletionPolicy.update_batch_completion_counters` now uses `CJBatchRepositoryProtocol.get_batch_state_for_update(..., for_update=True)` to obtain a row-locked `CJBatchState` snapshot before mutating callback counters, preventing lost updates under concurrent callbacks.
  - Tests updated in `services/cj_assessment_service/tests/unit/test_batch_completion_policy.py` to assert the `get_batch_state_for_update(..., for_update=True)` call in all counter update scenarios while preserving the existing behavioural assertions for `completed_comparisons`, `failed_comparisons`, `last_activity_at`, and `partial_scoring_triggered`.
- PR1/Continuation – Fresh pending-callback guard:
  - Added `services/cj_assessment_service/tests/unit/test_workflow_continuation_orchestration.py::test_finalization_skipped_when_fresh_pending_callbacks_detected` and `::test_finalization_proceeds_when_no_fresh_pending_callbacks` to lock in the new `_has_fresh_pending_callbacks` guard semantics around `ContinuationDecision.FINALIZE_SCORING`.
  - These tests ensure that both success and failure finalization paths consult a fresh batch-state snapshot and skip finalization when new callbacks are still in flight.
- CJ ↔ LPS serial-bundle hint semantics (shared with TASK-CJ-LLM-PROVIDER-BATCH-API-MODE):
  - CJ metadata hints:
    - Initial batches: `services/cj_assessment_service/tests/unit/test_llm_batching_metadata.py::test_submit_initial_batch_sets_preferred_bundle_size_to_wave_size` verifies that `ComparisonBatchOrchestrator.submit_initial_batch()` emits `preferred_bundle_size == len(comparison_tasks)` (per wave) and `<= 64`.
    - Retry batches: `services/cj_assessment_service/tests/unit/test_retry_logic.py::test_retry_batch_metadata_includes_capped_preferred_bundle_size` verifies that retry waves emit `preferred_bundle_size == 64` when more than 64 tasks are retried.
  - LPS hint parsing and bundling:
    - `services/llm_provider_service/tests/unit/test_llm_override_utils.py` covers `get_preferred_bundle_size_hint` for valid / invalid / out-of-range values.
    - `services/llm_provider_service/tests/unit/test_serial_bundle_strategy.py` asserts that:
      - For `preferred_bundle_size` below the cap, `SerialBundleStrategy.execute` limits the bundle size to the hint.
      - For `preferred_bundle_size` above the cap, bundling is capped at `settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL` (default 64).
  - Docker-level callback invariants for regular ENG5 batches:
    - Added `tests/integration/test_cj_regular_batch_callbacks_docker.py::TestCJRegularBatchCallbacksDocker::test_cj_regular_batch_callbacks_and_preferred_bundle_size_invariants` to drive a 24-essay ENG5 batch under the `cj_generic_batch` mock profile with `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=serial_bundle`, asserting that:
      - CJBatchState callback counters (`completed_comparisons + failed_comparisons`) match the number of `LLMComparisonResultV1` callbacks observed on the CJ LLM callback topic.
      - Any `preferred_bundle_size` values present in callback `request_metadata` are integers in the inclusive range `[1, 64]`.
      - No additional callbacks are observed for the batch once CJ has finalized scoring (based on `CJBatchUpload.completed_at` and callback `event_timestamp`).
    - The docker test is gated on `CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=true` to avoid running a full 24-essay ENG5 batch in environments where batching hints are disabled; when the flag is false the test skips quickly with an explicit message.
  - Cross-service metadata contract:
    - `tests/integration/test_cj_lps_metadata_roundtrip.py` now:
      - Allows CJ to send `preferred_bundle_size` in `LLMComparisonRequest.metadata`.
      - Expects `preferred_bundle_size` to be present (when provided) in `LLMComparisonResultV1.request_metadata` with invariants: `isinstance(value, int)` and `1 <= value <= 64`.
    - `services/llm_provider_service/tests/integration/test_serial_bundle_integration.py` extends the happy-path bundling test to include a `preferred_bundle_size` hint under the cap, ensuring that the size-2 bundle used in the test is compatible with the hint semantics.
  - End-to-end validation (regular ENG5 docker suite):
    - Wired `CJBatchUpload.completed_at` in `BatchFinalizer` for both success (`finalize_scoring`, `finalize_single_essay`) and failure (`finalize_failure`) paths, using naive UTC timestamps compatible with the `TIMESTAMP WITHOUT TIME ZONE` column.
    - Updated `tests/integration/test_cj_regular_batch_callbacks_docker.py` to normalize callback `event_timestamp` values to naive UTC before comparison with `CJBatchUpload.completed_at`, making the “no callbacks after finalization” assertion robust against naive/aware differences.
    - Verified that `pdm run eng5-cj-docker-suite regular` now passes end-to-end under `serial_bundle` + hint metadata:
      - `test_cj_regular_batch_resampling_metadata_completed_successful`
      - `test_cj_regular_batch_callbacks_and_preferred_bundle_size_invariants`
  - ENG5/CJ harness documentation:
    - `docs/operations/eng5-np-runbook.md` now includes an **ENG5/CJ serial-bundle test harness** subsection that:
      - Points at `tests/eng5_profiles/*` as ENG5 profile parity tests (separate from standard docker integration tests).
      - Documents `pdm run eng5-cj-docker-suite` and `pdm run llm-mock-profile <profile>` as the primary orchestration commands.
      - Provides `pdm run pytest-root ...` examples so individual docker/ENG5 test files can still be executed without running the full suite.

---

## PR 1 – CJ Batch Completion & Metrics Semantics Fix

**Goal:** Make batch completion, partial scoring, and metrics use coherent
counters so completion percentages never exceed 100% and match DB reality.

**Status:** in_progress (stability-first completion landed 2025-11-21)

**Files:**
- `services/cj_assessment_service/models_db.py` (`CJBatchState`)
- `cj_core_logic/callback_state_manager.py`
- `cj_core_logic/batch_completion_checker.py`
- `cj_core_logic/workflow_continuation.py`
- `cj_core_logic/batch_processor.py`

**Checklist (updated 2025-11-21):**
- **[x]** Define clear semantics for `total_comparisons`, `submitted_comparisons`,
  `completed_comparisons`, `failed_comparisons` (global budget vs runtime counts).
- **[x]** Keep `total_comparisons`/`total_budget` immutable per batch; accumulate `submitted_comparisons` per iteration.
- **[x]** Completion gate now uses callbacks_received (completed+failed) with denominator `min(total_budget or total_comparisons, nC2)`; small batches finalize immediately (n=4 → 6 pairs).
- **[x]** Stability-first: when callbacks_received == submitted_comparisons, recompute BT and finalize on stability (`SCORE_STABILITY_THRESHOLD`) or when callbacks hit denominator/budget cap; BatchMonitor stays recovery-only.
- **[±]** Partial scoring trigger still uses legacy 80% heuristic; leave for follow-up if needed (no regression today).
- **[x]** Tests added/updated: workflow continuation, completion denominator small-batch cap.
- **[x]** Validation: `pdm run pytest-root services/cj_assessment_service/tests/unit/test_workflow_continuation.py services/cj_assessment_service/tests/unit/test_completion_threshold.py` + lint/format.

**Progress 2025-12-09 (ENG5 heavy CI staging):**
- Added dedicated heavy CI workflow `.github/workflows/eng5-heavy-suites.yml` with two opt-in jobs (kept out of the default fast CI path):
  - `ENG5 CJ Docker Semantics (regular + small-net)` (`eng5-cj-docker-regular-and-small-net`):
    - Runs ENG5 CJ docker semantics under serial-bundle + hints using:
      - `pdm run eng5-cj-docker-suite regular`
      - `pdm run eng5-cj-docker-suite small-net`
    - Assumes `.env` config with:
      - `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=serial_bundle`
      - `CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=true`
      - `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=serial_bundle`
      - `LLM_PROVIDER_SERVICE_BATCH_API_MODE=disabled`
  - `ENG5 Mock Profile Parity Suite` (`eng5-profile-parity-suite`):
    - Validates CJ/LPS trace-based ENG5 profiles via `pdm run llm-mock-profile <profile>`:
      - `cj-generic`, `eng5-anchor`, `eng5-lower5` mapped to tests in `tests/eng5_profiles/*`.
    - Assumes `.env` mock profile settings:
      - `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true`
      - `LLM_PROVIDER_SERVICE_MOCK_MODE` in `{cj_generic_batch, eng5_anchor_gpt51_low, eng5_lower5_gpt51_low}` per profile.

**Planned Work – Step 1: Heavy-lane metrics assertions in ENG5 CJ docker tests (EPIC-005, EPIC-011):**
- Scope:
  - Extend ENG5 CJ docker semantics tests with Prometheus metrics assertions for serial bundling and completion **in Lane C only**:
    - `tests/functional/cj_eng5/test_cj_regular_batch_callbacks_docker.py`
    - `tests/functional/cj_eng5/test_cj_regular_batch_resampling_docker.py`
    - `tests/functional/cj_eng5/test_cj_small_net_continuation_docker.py`
- Constraints:
  - New metrics assertions MUST be exercised only via:
    - Local: `pdm run eng5-cj-docker-suite regular` / `small-net`.
    - CI: `eng5-cj-docker-regular-and-small-net` job in `.github/workflows/eng5-heavy-suites.yml`.
  - No changes to fast PR or walking-skeleton lanes (see EPIC-011 and Rule 101).
- Metrics to assert (non-exhaustive, guided by ENG5 runbook and metrics rules):
  - CJ:
    - `cj_llm_requests_total{batching_mode="serial_bundle"}`
    - `cj_llm_batches_started_total{batching_mode="serial_bundle"}`
    - `cj_batch_state` / `cj_batch_progress_percentage` for completion.
  - LPS:
    - `llm_provider_serial_bundle_calls_total{provider,model}`
    - `llm_provider_serial_bundle_items_per_call{provider,model}`
    - Queue wait-time metrics under `queue_processing_mode="serial_bundle"` where available.

**Progress 2025-12-10 – Initial metrics slice wired for regular ENG5 callbacks (Lane C only):**
- Shared metrics helper introduced for docker-backed tests:
  - File: `tests/utils/metrics_helpers.py`
  - Responsibilities: fetch `/metrics` via HTTP with a short timeout and parse Prometheus text into a mapping of `metric_name -> [(labels, value), ...]` for test assertions.
- `tests/functional/cj_eng5/test_cj_regular_batch_callbacks_docker.py` extended with CJ ↔ LPS metrics assertions in
  `test_cj_regular_batch_callbacks_and_preferred_bundle_size_invariants`:
  - CJ metrics asserted (serial-bundle semantics):
    - `cj_llm_requests_total{batching_mode="serial_bundle"}` – at least one request recorded (`max(values) >= 1`).
    - `cj_llm_batches_started_total{batching_mode="serial_bundle"}` – at least one batch started (`max(values) >= 1`).
  - LPS metrics asserted (bundling behaviour, derived from `/metrics` and service settings):
    - `llm_provider_serial_bundle_calls_total{provider=<default_provider>,model=<CJSettings.DEFAULT_LLM_MODEL>}` – at least one serial-bundle call (`max(values) >= 1`).
    - `llm_provider_serial_bundle_items_per_call{provider=<default_provider>,model=<CJSettings.DEFAULT_LLM_MODEL>}` – use `_count` and `_bucket` series to:
      - Confirm at least one observation (`_count >= 1`).
      - Infer an upper bound on `max(items_per_call)` from bucket counts and assert `1 <= max_items_per_call <= Settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL`.
  - This callbacks-focused slice serves as the template for the additional ENG5 CJ docker metrics coverage described below.

**Progress 2025-12-10 – Step 1 metrics now wired for all three ENG5 CJ docker tests:**
- Serial-bundle CJ ↔ LPS metrics assertions now exist in all three ENG5 CJ docker tests, reusing `tests/utils/metrics_helpers.py` and the same assertion shape as the callbacks test:
  - `tests/functional/cj_eng5/test_cj_regular_batch_resampling_docker.py` (regular-batch resampling path).
  - `tests/functional/cj_eng5/test_cj_small_net_continuation_docker.py` (LOWER5 small-net continuation path).
- For each test, after a successful ENG5 run the suite:
  - Uses `ServiceTestManager.get_validated_endpoints()` to obtain `metrics_url` for both `cj_assessment_service` and `llm_provider_service`.
  - Calls `fetch_and_parse_metrics(...)` to build an in-memory `metric_name -> [(labels, value), ...]` map.
  - Asserts on the CJ side that:
    - `cj_llm_requests_total{batching_mode="serial_bundle"}` is present and `max(values) >= 1`.
    - `cj_llm_batches_started_total{batching_mode="serial_bundle"}` is present and `max(values) >= 1`.
  - Asserts on the LPS side (for the active ENG5 provider/model pair, typically `provider=<default_provider>` and `model=<CJSettings.DEFAULT_LLM_MODEL>`):
    - `llm_provider_serial_bundle_calls_total{provider,model}` is present with `max(values) >= 1`.
    - `llm_provider_serial_bundle_items_per_call{provider,model}` uses the `_count` series and corresponding `_bucket` samples to:
      - Confirm at least one observation (`_count >= 1`).
      - Infer an upper bound on `max(items_per_call)` and assert `1 <= max_items_per_call <= Settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL`.
- These three tests have been validated green via the ENG5 harness in at least one environment:
  - `pdm run eng5-cj-docker-suite regular` (callbacks + resampling).
  - `pdm run eng5-cj-docker-suite small-net` (LOWER5 continuation).
- Queue wait-time and deeper queue hygiene metrics for serial-bundle (`llm_provider_queue_wait_time_seconds{queue_processing_mode="serial_bundle",result=...}` and related series) remain out of scope for Step 1 and are planned as part of Step 2 parity-focused work (see `TASKS/infrastructure/llm-mock-provider-cj-behavioural-parity-tests.md` and LPS queue hygiene tasks).

**Progress 2025-12-10 (session 4) – ENG5 CI fixes and provider switch COMPLETED:**
- **Default LLM provider switched from Anthropic to OpenAI:**
  - `services/llm_provider_service/config.py`: `DEFAULT_LLM_PROVIDER` → `LLMProviderType.OPENAI`
  - `services/llm_provider_service/config.py`: `OPENAI_DEFAULT_MODEL` → `gpt-5.1`
  - `services/cj_assessment_service/config.py`: `DEFAULT_LLM_MODEL` → `gpt-5.1`
  - `docker-compose.services.yml`: CJ defaults from `anthropic/claude-haiku-4-5-20251001` → `openai/gpt-5.1`
- **USE_MOCK_LLM alias fully deprecated:**
  - `env.example`: `USE_MOCK_LLM=true` → `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true`
  - `docker-compose.services.yml`: Removed `${USE_MOCK_LLM:-true}` alias
  - Updated 10+ documentation files with canonical env var
- **Positional fairness test fixed:**
  - Root cause: `MAX_PAIRWISE_COMPARISONS=120` too low for 24-essay batch (skew ~0.6 vs threshold 0.2)
  - Fix: Added `CJ_ASSESSMENT_SERVICE_MAX_PAIRWISE_COMPARISONS=288` to CI workflow `.env` generation
- **All ENG5 docker suites validated:**
  - `pdm run eng5-cj-docker-suite regular` ✅ (callbacks + resampling tests pass)
  - `pdm run eng5-cj-docker-suite small-net` ✅ (LOWER5 continuation test passes)
  - `pdm run llm-mock-profile cj-generic` ✅
  - `pdm run llm-mock-profile eng5-anchor` ✅
  - `pdm run llm-mock-profile eng5-lower5` ✅
- **Code quality validated:** `format-all`, `lint-fix`, `typecheck-all` all pass

**Progress 2025-12-10 (session 5) – Step 2 ENG5 mock profile metrics wired and validated:**
- Shared LPS metrics helper for ENG5 mock profiles (`tests/eng5_profiles/eng5_lps_metrics_assertions.py`) is now exercised by all three profile suites:
  - CJ generic: `tests/eng5_profiles/test_cj_mock_parity_generic.py`
  - ENG5 full-anchor: `tests/eng5_profiles/test_eng5_mock_parity_full_anchor.py`
  - ENG5 LOWER5: `tests/eng5_profiles/test_eng5_mock_parity_lower5.py`
- Metrics pinned per ENG5 profile run (all via `/metrics` on `llm_provider_service` and `ServiceTestManager.get_validated_endpoints()`):
  - Serial-bundle calls:
    - `llm_provider_serial_bundle_calls_total{provider="mock",model=<profile_model>}` – at least one call recorded for the dominant mock model (`max(values) >= 1`).
  - Items per call distribution:
    - `llm_provider_serial_bundle_items_per_call_count{provider="mock",model=<profile_model>}` – at least one observation (`_count >= 1`) used as the total call count.
    - `llm_provider_serial_bundle_items_per_call_bucket{provider="mock",model=<profile_model>,le=*}` – bucket scan used to infer an upper bound on `max(items_per_call)` with the inequality guardrail `1 <= max_items_per_call <= Settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL`.
  - Queue wait-time guardrail (serial_bundle mode):
    - `llm_provider_queue_wait_time_seconds_count{queue_processing_mode="serial_bundle"}` and `_sum` – ensure at least one sample across results.
    - Derived `average_wait_seconds = sum / count` must satisfy:
      - `average_wait_seconds >= 0.0`
      - `average_wait_seconds <= 120.0` (broad guardrail suitable for ENG5 heavy runs; catches clearly broken queue behaviour without over-constraining CI).
    - `result` label set for at least one of `{success,failure,expired}` and `result` set ⊆ `{success,failure,expired}`.
  - Comparison callbacks:
    - `llm_provider_comparison_callbacks_total{queue_processing_mode="serial_bundle"}` – at least one callback recorded (`max(values) >= 1`).
  - Queue depth:
    - `llm_provider_queue_depth{queue_type="total"}` – if present, must stay comfortably below configured `QUEUE_MAX_SIZE` (asserted `max(values) <= 1000.0` for current settings).
- Profile-specific behavioural assertions now combined with metrics guardrails:
  - CJ generic:
    - Single-batch and multi-batch tests enforce 100% Essay A winners, token/latency parity vs `cj_lps_roundtrip_mock_20251205`, then call the LPS metrics helper.
  - ENG5 full-anchor:
    - 12-anchor/66-comparison parity vs `eng5_anchor_align_gpt51_low_20251201` with a 20 percentage point tolerance on per-label winner proportions and token/latency parity, then LPS metrics guardrails (including relaxed queue wait bound).
  - ENG5 LOWER5:
    - `test_eng5_mock_parity_lower5_mode_matches_recorded_summary` remains the primary parity test vs `eng5_lower5_gpt51_low_20251202` and now also calls the LPS metrics helper.
    - `test_eng5_mock_lower5_small_net_diagnostics_across_batches` drives 3×10 LOWER5-shaped small-net batches and asserts:
      - Each anchor pair appears exactly once per batch and exactly `num_batches` times overall.
      - Winners per pair are stable across batches.
      - Aggregate winner proportions preserve the “Essay B majority” shape while allowing per-label drift up to ±0.20 from the recorded trace (reframed as a canary instead of a brittle 10% parity pin on a 10-comparison net).
      - Token and latency metrics remain within the same inequality bands as the canonical LOWER5 parity test.
      - LPS metrics guardrails from the shared helper all hold at the end of the diagnostics run.
- Heavy C-lane validation (all executed this session with correct `.env` profiles):
  - `pdm run llm-mock-profile cj-generic` ✅ (CJ generic parity + coverage, including LPS metrics helper).
  - `pdm run llm-mock-profile eng5-anchor` ✅ (ENG5 anchor parity + LPS metrics helper with `average_wait_seconds <= 120.0`).
  - `pdm run llm-mock-profile eng5-lower5` ✅ (ENG5 LOWER5 parity + small-net diagnostics and LPS metrics helper).
- These ENG5 profile parity suites now consume the same LPS serial-bundle and queue metrics introduced in Step 1, but scoped to `{provider="mock",model=<profile_model>}` and driven by the mock profile harness rather than CJ docker semantics tests.

---

## PR 2 – Pair Generation Fairness & Anchor Position Balancing

**Goal:** Remove structural bias where anchors dominate `essay_a` and ensure
balanced A/B positions while preserving reproducibility.

**Status:** todo

**Files:**
- `cj_core_logic/pair_generation.py`
- `cj_core_logic/batch_preparation.py`
- `config.py` (optional toggle)

**Checklist:**
- **[ ]** Introduce an optional deterministic shuffle of `essays_for_comparison`
  (seeded by `cj_batch_id` and iteration) before generating pairs when
  `ENABLE_COMPARISON_POSITION_BALANCING` is true.
- **[ ]** At pair creation time, randomly (but deterministically) decide whether
  to swap A/B for each pair so that frequent essays appear in both positions.
- **[ ]** Preserve duplicate-prevention by continuing to normalise pair keys via
  sorted IDs.
- **[ ]** Ensure anchors still carry `processing_metadata.is_anchor = True` and
  all grade metadata so BT/grade projection logic remains correct.
- **[ ]** Add tests that show anchors and students are no longer stuck in a
  single position when they appear in multiple pairs.
- **[ ]** Add a small diagnostic helper (or extend an existing script) to print
  per-batch A/B counts per essay and summarise anchor vs student distributions.

---

## PR 3 – Anthropic Error Diagnostics for Serial-Bundle ENG5 Runs

**Goal:** Classify Anthropic errors (rate limit, overload, max_tokens truncation) and surface
them via structured `ErrorDetail` and Prometheus metrics so ENG5 runs can distinguish provider behaviour from CJ bugs.

**Status:** in_progress (retry/overload/stop_reason + prompt caching shipped 2025-11-21)

**Files:**
- `services/llm_provider_service/implementations/anthropic_provider_impl.py`
- `services/llm_provider_service/config.py`
- `services/llm_provider_service/exceptions.py`
- `services/llm_provider_service/metrics.py`

**Checklist (current):**
- **[x]** Treat 529/`overloaded_error` as transient + retryable; metrics label `overloaded`.
- **[x]** Respect `Retry-After` on 429 (bounded sleep) and propagate retryable details.
- **[x]** Detect `stop_reason=max_tokens` and raise structured EXTERNAL_SERVICE_ERROR.
- **[x]** Include `correlation_id` + `prompt_sha256` in Anthropic request metadata; prompt caching hook on system block with configurable TTL.
- **[ ]** Extend `test_anthropic_error_diagnostics.py` to cover 529 / stop_reason flows (currently 429/500/connection).
- **[ ]** Add PromQL snippets to LPS README or ENG5 runbook for error_type visibility.

---

## PR 4 – Queue Hygiene & Orphan Callback Handling

**Goal:** Ensure stuck queue items and orphan callbacks (unknown correlation IDs)
are detectable and do not silently affect ENG5 runs.

**Status:** todo

**Files:**
- `services/llm_provider_service/implementations/queue_processor_impl.py`
- `services/llm_provider_service/queue_models.py`
- `services/llm_provider_service/metrics.py`
- `services/cj_assessment_service/cj_core_logic/callback_state_manager.py`
- `services/cj_assessment_service/message_handlers/llm_callback_handler.py`

**Checklist:**
- **[ ]** Add a configurable timeout for `QueueStatus.PROCESSING`; if a request
  exceeds it, mark as `EXPIRED` or `FAILED` and record metrics.
- **[ ]** Ensure `_periodic_cleanup` (or equivalent) runs this check and logs
  stuck items with CJ metadata when present (e.g. `cj_batch_id`).
- **[ ]** In `update_comparison_result`, when no `ComparisonPair` is found for a
  callback correlation ID, record a CJ metric
  `cj_orphan_callbacks_total{source_service}` and log structured details rather
  than only raising.
- **[ ]** Add unit tests for both stuck-queue cleanup and orphan callbacks.

---

## Summary & Validation Plan

- **[ ]** After PRs 1–4, re-run ENG5 `per_request` and `serial_bundle` executes
  with identical configuration and compare:
  - Error rates by provider/error_type.
  - A/B position distributions by anchor vs student.
  - CJ batch completion logs vs true DB counts.
- **[ ]** Update this task status and related TASK docs once validation is
  complete.
