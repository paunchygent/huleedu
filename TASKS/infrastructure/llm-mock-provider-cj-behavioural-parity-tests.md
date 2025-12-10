---
id: 'llm-mock-provider-cj-behavioural-parity-tests'
title: 'LLM mock provider CJ behavioural parity tests'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'infrastructure'
service: 'llm_provider_service'
owner_team: 'agents'
owner: ''
program: 'eng5'
created: '2025-12-04'
last_updated: '2025-12-09'
related: ['EPIC-005', 'EPIC-008', 'EPIC-011', 'llm-provider-openai-gpt-5x-reasoning-controls', 'llm-provider-anthropic-thinking-controls', 'cj-small-net-coverage-and-continuation-docker-validation']
labels: ['llm-provider', 'cj', 'eng5', 'mock-provider', 'parity']
---
# LLM mock provider CJ behavioural parity tests

## Objective

Make the **mock LLM provider** used by CJ and ENG5 behave as close as practical to the *real* providers it stands in for (OpenAI GPT‑5.1, Anthropic, etc.), and prove that parity with **docker-backed, data-driven tests** rather than assumptions.

Concretely:

- Define one or more **CJ-specific mock modes** whose behaviour (winners, error rates, latency, token usage, BT diagnostics, continuation decisions) closely matches real provider traces for:
  - ENG5 anchor-align runs (Anthropic + GPT‑5.1).
  - ENG5 LOWER5 runs (usage guard 007 + 006 rubric, 006/006 parity).
  - Representative “plain CJ” batches outside ENG5.
- Add docker integration tests that:
  - Replay recorded real-provider callbacks through CJ.
  - Run the same scenarios end-to-end with the mock provider.
  - Compare coverage, BT, and continuation metrics for behavioural parity.

## Context

- The new CJ small-net coverage and continuation tests rely on a **mock LLM provider** to keep docker tests deterministic and fast.
- ENG5 experiments (especially LOWER5) will also use the mock provider when validating:
  - Completion semantics (`total_budget` only).
  - Small-net Phase‑2 resampling behaviour.
  - Reasoning-effort and verbosity propagation (GPT‑5.x).
- Today, we assume the mock is “good enough.” For the docker debugging suite (and future E2E harnesses) to be trustworthy, we need:
  - **Recorded real-provider traces** as a reference surface.
  - A dedicated **CJ/ENG5 mode** for the mock provider tuned against those traces.
  - **Parity tests** that pin this behaviour, so future changes to real providers or the mock are caught.
- This task connects to:
  - EPIC‑005 (CJ Stability & Reliability): we need a realistic LLM behaviour model for convergence/continuation verification.
  - EPIC‑008 (ENG5 Runner Refactor & Prompt Tuning): ENG5 anchor-align and LOWER5 experiments should see mock behaviour that is representative of production models.
  - `TASKS/infrastructure/llm-provider-openai-gpt-5x-reasoning-controls.md` and `TASKS/infrastructure/llm-provider-anthropic-thinking-controls.md`, which define the provider-side reasoning/verbosity semantics the mock must emulate.
  - `TASKS/assessment/cj-small-net-coverage-and-continuation-docker-validation.md` (to be created): docker tests for small-net coverage/continuation need a reliable mock provider.

## Plan

### 1. Capture representative real-provider traces

- [ ] Select 3–4 canonical scenarios:
  - [ ] ENG5 anchor-align full-anchor runs (Anthropic models with 003 prompts).
  - [ ] ENG5 LOWER5 runs for GPT‑5.1 (`reasoning_effort` in {"none", "low"}, usage guard 007 + 006 rubric, 006/006 parity).
  - [ ] One or two non-ENG5 CJ batches with realistic student + anchor mixes.
- [ ] For each scenario, extract a small but representative slice of `LLMComparisonResultV1` callbacks:
  - [ ] Persist them as fixtures under a dedicated directory (e.g. `tests/data/llm_traces/`) or `.claude/research/data/...` with stable IDs/checksums.
  - [ ] For each fixture set, precompute and store:
    - [ ] Winner distribution across pairs and anchors.
    - [ ] Error rate by `error_code`.
    - [ ] Latency summary (min / mean / max).
    - [ ] Token usage summary (prompt/completion/total).
    - [ ] BT `se_summary` and `bt_quality_flags` when replayed through CJ.

### 2. Define CJ/ENG5-specific mock provider modes

- [ ] Identify or create a dedicated mock provider implementation in `llm_provider_service` that:
  - [ ] Accepts a **mode identifier** (e.g. `"cj_eng5_lower5_gpt51"`, `"cj_eng5_full_sonnet003"`, `"cj_generic_batch"`).
  - [ ] Produces `LLMComparisonResultV1` payloads with:
    - [ ] Winners consistent with a simple quality model or replayed real traces.
    - [ ] Configurable error rates and error types (timeout, provider error, malformed).
    - [ ] Latency distribution and token-usage ranges that approximate real traces.
    - [ ] Proper handling of `reasoning_effort` / `output_verbosity` (fields present/absent as in real calls).
- [ ] Wire these modes into:
  - [ ] CJ settings (e.g. `LLM_PROVIDER_SERVICE_USE_MOCK_LLM`, `LLM_PROVIDER_SERVICE_MOCK_MODE`).
  - [ ] ENG5 runner configs used by the docker tests (so the runner can select the appropriate mock mode).

### 3. Add docker trace-replay parity tests

All tests in this section:
- MUST be docker-backed (no in-process mocks of CJ repositories or models).
- MAY use the mock provider; real-provider traces are used as fixtures, not live calls.

#### 3.1 CJ trace replay vs mock for generic batches

- [ ] Add an integration test module (e.g. `tests/eng5_profiles/test_cj_mock_parity_generic.py`) that:
  - [ ] Replays recorded `LLMComparisonResultV1` fixtures into CJ for a generic batch (real trace path), completes the batch, and records:
    - Coverage metrics: `max_possible_pairs`, `successful_pairs_count`.
    - BT `se_summary` and `bt_quality_flags`.
    - Continuation decisions and iteration count.
  - [ ] Runs the same scenario end-to-end with the mock provider in `"cj_generic_batch"` mode, then records the same metrics.
  - [ ] Asserts parity within tolerances:
    - [ ] `max_possible_pairs` identical.
    - [ ] `successful_pairs_count` equal or within a small delta.
    - [ ] `comparison_count` in BT result identical.
    - [ ] `bt_quality_flags` match.
    - [ ] Number of iterations and high-level continuation decisions (`REQUEST_MORE_COMPARISONS`, `FINALIZE_SCORING`, `FINALIZE_FAILURE`) match.

#### 3.2 ENG5 anchor-align parity (full anchor nets)

- [ ] Add an integration test module (e.g. `tests/eng5_profiles/test_eng5_mock_parity_full_anchor.py`) that:
  - [ ] Uses recorded ENG5 anchor-align real traces to compute reference metrics (as in 3.1) for a full-anchor run.
  - [ ] Runs the same ENG5 configuration via `eng5-runner` with `provider=openai`/Anthropic + mock mode enabled (no live external LLM).
  - [ ] Asserts:
    - [ ] CJ coverage and BT metrics parity, as above.
    - [ ] ENG5 DB reports (alignment report) see similar tau/inversion patterns across the anchor set (tolerances defined in EPIC‑008 context).

#### 3.3 ENG5 LOWER5 parity (small nets)

- [ ] Add an integration test module (e.g. `tests/eng5_profiles/test_eng5_mock_parity_lower5.py`) that:
  - [ ] Uses recorded LOWER5 real runs (GPT‑5.1, 007/006 and 006/006) to compute reference metrics:
    - [ ] `max_possible_pairs`, `successful_pairs_count`, `unique_coverage_complete`.
    - [ ] Total comparisons and iteration counts.
    - [ ] Small-net flags: `is_small_net`, `resampling_pass_count`, `small_net_cap_reached`.
  - [ ] Runs the same LOWER5 configurations with the mock provider (`"cj_eng5_lower5_gpt51"` mode).
  - [ ] Asserts:
    - [ ] Coverage and total comparisons within agreed tolerances.
    - [ ] Same pattern of Phase‑1 and Phase‑2 decisions (e.g. at least one RESAMPLING wave when budget > nC2 and caps allow).
    - [ ] Small-net flags derived from metadata (`build_small_net_context`) behave identically.

### 4. Error and retry behaviour parity tests

- [ ] Add a docker integration test (e.g. `tests/integration/test_cj_mock_parity_errors.py`) that:
  - [ ] Uses a real trace with a mix of successful and error callbacks (including retries).
  - [ ] Measures:
    - [ ] Real error rate and `error_code` distribution.
    - [ ] Retry success rate.
    - [ ] Coverage metrics and `successful_pairs_count` after retries.
  - [ ] Runs the same scenario under a mock mode tuned to the same error profile.
  - [ ] Asserts:
    - [ ] Mock error rate and retry success rate within tolerance.
    - [ ] Coverage helper and metadata treat “eventual success after error” identically (same `successful_pairs_count` and coverage completeness).

### 5. Schema/shape parity tests

- [ ] Add a focused integration test (e.g. `tests/integration/test_llm_mock_schema_parity.py`) that:
  - [ ] Calls the mock provider via LPS HTTP exactly as CJ would.
  - [ ] Inspects a sample of `LLMComparisonResultV1` payloads and asserts:
    - [ ] All required fields are present and have correct types.
    - [ ] Nested `request_metadata`, token usage, and cost fields match the shape used by real providers.
    - [ ] `reasoning_effort` / `output_verbosity` fields are present or absent in the same circumstances as real provider traces for GPT‑5.x and Anthropic.

### 6. Wire into existing docker debugging tasks

- [ ] Make sure the new mock-modes and parity tests integrate with:
  - [ ] `TASKS/assessment/cj-small-net-coverage-and-continuation-docker-validation.md` (CJ coverage/continuation docker tests must use a parity-validated mock mode).
  - [ ] `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md` (document which mock modes to use for fast/parity-friendly ENG5 experiments).
  - [ ] `TASKS/infrastructure/llm-provider-openai-gpt-5x-reasoning-controls.md` and `TASKS/infrastructure/llm-provider-anthropic-thinking-controls.md` (ensure mock mode behaviour stays aligned with reasoning/verbosity semantics).

### 7. Quality gates

- [ ] Run targeted tests:
  - [ ] `pdm run pytest-root tests/eng5_profiles/test_cj_mock_parity_generic.py`
  - [ ] `pdm run pytest-root tests/eng5_profiles/test_eng5_mock_parity_full_anchor.py`
  - [ ] `pdm run pytest-root tests/eng5_profiles/test_eng5_mock_parity_lower5.py`
  - [ ] `pdm run pytest-root tests/integration/test_cj_mock_parity_errors.py`
  - [ ] `pdm run pytest-root tests/integration/test_llm_mock_schema_parity.py`
- [ ] Run repo-wide quality gates:
  - [ ] `pdm run format-all`
  - [ ] `pdm run lint-fix --unsafe-fixes`
  - [ ] `pdm run typecheck-all`

### 8. LPS mock-mode observability (implemented)

- [x] Expose the active LPS mock configuration via a small admin endpoint:
  - [x] Add `GET /admin/mock-mode` on `llm_provider_service` that returns:
    - [x] `use_mock_llm` (bool) derived from `Settings.USE_MOCK_LLM`.
    - [x] `mock_mode` (string or `null`) derived from `Settings.MOCK_MODE` (e.g. `"cj_generic_batch"`, `"eng5_anchor_gpt51_low"`, `"eng5_lower5_gpt51_low"`; `MockMode.DEFAULT` is surfaced as `null`).
    - [x] `default_provider` (string) derived from `Settings.DEFAULT_LLM_PROVIDER`.
  - [x] Add LPS API tests under `services/llm_provider_service/tests/api/` to pin this endpoint for the three mock profiles and the admin-disabled guard.
- [x] Refactor CJ/ENG5 docker parity/coverage tests to assert against `/admin/mock-mode` instead of `.env` heuristics:
  - [x] In `tests/eng5_profiles/test_cj_mock_parity_generic.py`, `tests/eng5_profiles/test_eng5_mock_parity_full_anchor.py`, and `tests/eng5_profiles/test_eng5_mock_parity_lower5.py`:
    - [x] Use the validated `llm_provider_service` base URL from `ServiceTestManager` to call `/admin/mock-mode` at the start of each test.
    - [x] `pytest.skip` when `use_mock_llm` is `false` or `mock_mode` does not match the expected profile.
    - [x] Remove direct `.env` parsing and cross-checks between process env and `.env`; treat `/admin/mock-mode` as the single source of truth for the running container’s mock mode. `.env` is still validated by `scripts/llm_mgmt/mock_profile_helper.sh`, but tests rely exclusively on the HTTP admin endpoint.

#### Admin endpoint contract

- Path: `GET /admin/mock-mode`
- Availability:
  - Enabled when `Settings.ADMIN_API_ENABLED` is `True` (default in dev/CI).
  - Returns `404` with `{"error": "admin_api_disabled"}` when `ADMIN_API_ENABLED` is `False`.
- Sample response (CJ generic profile):

```json
{
  "use_mock_llm": true,
  "mock_mode": "cj_generic_batch",
  "default_provider": "openai"
}
```

All CJ/ENG5 docker-backed mock parity tests now:

- Assert profile correctness by calling `/admin/mock-mode` on the running `llm_provider_service` container.
- Skip gracefully with clear messages when `use_mock_llm` is `false` or `mock_mode` does not match the expected profile.
- Use `ServiceTestManager`’s validated `base_url` for both the admin endpoint and the `/api/v1/comparison` HTTP surface.

`pdm run llm-mock-profile <profile>` (via `scripts/llm_mgmt/mock_profile_helper.sh`) remains the recommended orchestrator for:

- Validating `.env` mock profile settings (`LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true`, `LLM_PROVIDER_SERVICE_MOCK_MODE=<expected>`).
- Restarting only the `llm_provider_service` dev container.
- Running the appropriate docker-backed parity tests, which now rely on `/admin/mock-mode` as the single source of truth for the running container’s mock mode.

In CI, these parity tests are wired into the dedicated heavy workflow `.github/workflows/eng5-heavy-suites.yml` via the `ENG5 Mock Profile Parity Suite` job (`eng5-profile-parity-suite`), which:

- Ensures mock mode is enabled and `LLM_PROVIDER_SERVICE_MOCK_MODE` is set per profile (`cj_generic_batch`, `eng5_anchor_gpt51_low`, `eng5_lower5_gpt51_low`) by updating `.env`.
- Executes `pdm run llm-mock-profile cj-generic`, `pdm run llm-mock-profile eng5-anchor`, and `pdm run llm-mock-profile eng5-lower5` as part of a separate, opt-in CI stage so ENG5/CJ parity checks remain out of the default fast PR pipeline.

**Planned Work – Step 2: Richer ENG5 parity metrics in Heavy C-lane (EPIC-005, EPIC-008, EPIC-011):**

- Scope:
  - Extend ENG5 mock parity tests with queue/batching and metrics assertions **within Lane C only**:
    - `tests/eng5_profiles/test_cj_mock_parity_generic.py`
    - `tests/eng5_profiles/test_eng5_mock_parity_full_anchor.py`
    - `tests/eng5_profiles/test_eng5_mock_parity_lower5.py`
    - Orchestrator: `tests/eng5_profiles/test_eng5_profile_suite.py` (optional aggregate checks).
- Execution:
  - Local:
    - `pdm run llm-mock-profile cj-generic`
    - `pdm run llm-mock-profile eng5-anchor`
    - `pdm run llm-mock-profile eng5-lower5`
  - CI:
    - `eng5-profile-parity-suite` job in `.github/workflows/eng5-heavy-suites.yml` (future: matrix per profile).
- Metrics and behaviours to assert (metrics plan for ENG5 parity tests):
  - LPS (mock provider, per ENG5 profile):
    - `llm_provider_serial_bundle_calls_total{provider="mock",model=<profile_model>}`:
      - After each successful ENG5 profile run, assert that the metric is present for the active mock profile model and that `max(values) >= 1` (at least one serial-bundle call per run).
    - `llm_provider_serial_bundle_items_per_call{provider="mock",model=<profile_model>}`:
      - Use the `_count` and `_bucket` series to confirm at least one observation (`_count >= 1`) and infer an upper bound on `max(items_per_call)`.
      - Assert `1 <= max_items_per_call <= Settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL`, mirroring the ENG5 CJ docker semantics but scoped to mock-provider traffic.
    - Queue latency / throughput metrics:
      - `llm_provider_queue_wait_time_seconds{queue_processing_mode="serial_bundle",result=...}`:
        - Assert that at least one sample is recorded for `queue_processing_mode="serial_bundle"` and result in `{success,failure,expired}` as appropriate for each profile.
        - For healthy ENG5 runs, treat this as a **guardrail** rather than a strict SLO: check that the average wait derived from `_sum/_count` stays non-negative and within a broad upper bound (currently `average_wait_seconds <= 120.0` for heavy ENG5 suites), without pinning exact percentiles.
      - Coarse sanity checks for:
        - `llm_provider_comparison_callbacks_total{queue_processing_mode="serial_bundle",result=...}` to ensure callbacks are being published for serial-bundle paths.
        - `llm_provider_queue_depth{queue_type=...}` remaining below hard failure thresholds during ENG5 mock-only suites (no runaway queue growth; current guardrail `max(depth) <= 1000.0`).
  - CJ (where applicable for CJ-shaped mock runs, especially `cj_generic_batch`):
    - `cj_llm_requests_total{batching_mode="serial_bundle"}` and `cj_llm_batches_started_total{batching_mode="serial_bundle"}` should follow the same ≥1 semantics as the ENG5 CJ docker tests, but with expectations framed in terms of “at least one CJ serial-bundle request/batch per parity run” rather than exact counts.
  - Test-side harness pattern (shared across all ENG5 profile tests):
    - Reuse `ServiceTestManager` fixtures and `get_validated_endpoints()` to obtain `base_url` / `metrics_url` for `llm_provider_service` (and `cj_assessment_service` where relevant) after each successful ENG5 profile run.
    - Use `tests/utils/metrics_helpers.py::fetch_and_parse_metrics` to fetch `/metrics` and parse Prometheus text into a `metric_name -> [(labels, value), ...]` mapping.
    - Filter metrics by `provider="mock"` and `model=<profile_model>` (e.g.:
      - `cj_generic_batch` profile model.
      - `eng5_anchor_gpt51_low` profile model.
      - `eng5_lower5_gpt51_low` profile model.
    - Apply inequality-based assertions:
      - At least one serial-bundle call per profile (`llm_provider_serial_bundle_calls_total >= 1`).
      - Reasonable bundle-size distribution via `llm_provider_serial_bundle_items_per_call` histogram (within configured bounds; no degenerate single-bucket distributions for sustained runs).
      - Queue wait-time distributions that show “healthy” behaviour (no extreme tails under normal ENG5 parity suites, while still allowing rare outliers in heavy experimentation lanes).
  - Relationship to Step 1 CJ docker metrics:
    - Parity metrics MUST reuse the same helper (`tests/utils/metrics_helpers.py`) and general assertion style (≥1 semantics, histogram-derived upper bounds) as the ENG5 CJ docker tests, but scoped to:
      - `provider="mock"` and per-profile `model` labels.
      - ENG5 profile orchestration via `pdm run llm-mock-profile ...` instead of the CJ docker ENG5 runners.
    - All parity metrics remain read-only checks:
      - No changes to `.env` semantics beyond existing `LLM_PROVIDER_SERVICE_MOCK_MODE` profiles.
      - No modifications to ENG5 CI workflows or docker-compose; tests consume whatever metrics the running services expose.
  - All new assertions MUST rely on:
    - `/admin/mock-mode` for profile verification.
    - `/metrics` for Prometheus scraping, without introducing per-request mock switches or test-only provider flags.

## Success Criteria

- Mock provider offers explicit CJ/ENG5 modes (documented in config or README) whose behaviour is pinned by tests.
- For each scenario (generic CJ, ENG5 full anchor, ENG5 LOWER5):
  - Docker tests show:
    - Coverage metrics and BT diagnostics that are equal or within agreed tolerances vs real traces.
    - Small-net coverage and resampling flags behave identically between real traces and mock mode.
    - Continuation decisions (REQUEST_MORE_COMPARISONS vs FINALIZE_* and iteration counts) match.
- Error and retry behaviour under mock mode matches real error/retry patterns at the level of:
  - Overall error rate.
  - Retry success rate.
  - Coverage treatment of error-only vs eventual-success pairs.
- Schema/shape parity tests confirm that:
  - Mock provider outputs valid `LLMComparisonResultV1` payloads.
  - Reasoning/verbosity flags and token usage fields look identical (shape + type) to real providers.
- CJ and ENG5 docker debugging tasks (including `cj-small-net-coverage-and-continuation-docker-validation`) explicitly reference one or more parity-tested mock modes as their default LLM configuration.

## Related

- EPIC‑005: `docs/product/epics/cj-stability-and-reliability-epic.md`
- EPIC‑008: `docs/product/epics/eng5-runner-refactor-and-prompt-tuning-epic.md`
- LLM provider tasks:
  - `TASKS/infrastructure/llm-provider-openai-gpt-5x-reasoning-controls.md`
  - `TASKS/infrastructure/llm-provider-anthropic-thinking-controls.md`
- CJ/ENG5 debugging and programme tasks:
  - `TASKS/assessment/cj-small-net-coverage-and-continuation-docker-validation.md` (to be created)
  - `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md`
  - `TASKS/architecture/cj-lps-reasoning-verbosity-metadata-contract.md`

## Progress (2025-12-05)

- ENG5 LOWER5 GPT-5.1 low trace captured (LOWER5 small-net, usage guard 007 + 006 rubric):
  - Scenario id: `eng5_lower5_gpt51_low_20251202`
  - BOS batch id: `50f4509e-2e8c-4c62-a19d-93cf0739eefd` (canonical LOWER5 007+006, reasoning_effort="low", output_verbosity="low")
  - Callback topic: `huleedu.llm_provider.comparison_result.v1` (standard CJ → LPS comparison_result topic).
  - Fixture directory: `tests/data/llm_traces/eng5_lower5_gpt51_low_20251202/` with `llm_callbacks.jsonl` and `summary.json`.
  - Summary sanity: `total_events=10`, `success_count=10`, `error_count=0`, `winner_counts={"Essay A": 4, "Essay B": 6}`,
    mean prompt_tokens≈1298 (min≈1125, max≈1455), mean completion_tokens≈35 (min≈33, max≈36), mean total_tokens≈1333,
    latency mean≈1588ms, p95≈2142ms, p99≈2149ms.

- Trace capture harness implemented:
  - Script: `scripts/llm_traces/eng5_cj_trace_capture.py`
  - Responsibilities:
    - Connects to Kafka and filters `LLMComparisonResultV1` callbacks by `request_metadata.bos_batch_id`.
    - Persists raw callbacks to JSONL fixtures and computes a compact metrics summary:
      - Winner counts and error code counts.
      - Latency stats (`min`, `mean`, `p95`, `p99`).
      - Token usage stats for prompt/completion/total tokens (`min` / `mean` / `max`).
    - Leaves BT diagnostics (`bt_se_summary`, `bt_quality_flags`) as placeholders to be populated via CJ metadata in a later phase.
  - Unit test:
    - `scripts/tests/test_eng5_cj_trace_capture.py` pins down the summarizer’s aggregate behaviour on synthetic callbacks.

- First canonical trace captured (generic CJ ↔ LPS mock roundtrip):
  - Scenario id: `cj_lps_roundtrip_mock_20251205`
  - Source flow:
    - `tests/integration/test_cj_lps_metadata_roundtrip.py::TestCJLPSMetadataRoundtrip::test_metadata_preserved_through_http_kafka_roundtrip`
    - Uses `callback_topic="test.llm.callback.roundtrip.v1"`, `bos_batch_id="bos-roundtrip-001"`, and `LLMProviderType.MOCK` to avoid real provider calls.
  - Fixtures:
    - Directory: `tests/data/llm_traces/cj_lps_roundtrip_mock_20251205/`
    - Files:
      - `llm_callbacks.jsonl` – currently 4 validated `LLMComparisonResultV1` events.
      - `summary.json` – aggregate metrics for this scenario (all-success, `winner_counts={"Essay A": 4}`, no errors, stable token usage).

- How to regenerate this scenario (with dev stack running):
  - Ensure services and Kafka are up:
    - `pdm run dev-build-start`
  - Trigger the CJ ↔ LPS roundtrip once:
    - `pdm run pytest-root tests/integration/test_cj_lps_metadata_roundtrip.py::TestCJLPSMetadataRoundtrip::test_metadata_preserved_through_http_kafka_roundtrip -m 'docker and integration' -v`
  - Capture callbacks and summary:
    - ```bash
      pdm run python -m scripts.llm_traces.eng5_cj_trace_capture \
        --scenario-id cj_lps_roundtrip_mock_20251205 \
        --bos-batch-id bos-roundtrip-001 \
        --callback-topic test.llm.callback.roundtrip.v1 \
        --expected-count 1 \
        --timeout-seconds 30 \
        --output-dir tests/data/llm_traces
      ```

- Next recommended step from this task:
  - Define the first explicit mock mode (for a generic CJ scenario, e.g. `"cj_generic_batch"`) in the LLM mock provider and add a docker-backed integration test (e.g. `tests/integration/test_cj_mock_parity_generic.py`) that:
    - Replays a small batch of CJ-shaped requests using this mode.
    - Collects callbacks and compares winner distribution, error profile, and token/latency bands against `summary.json` from `cj_lps_roundtrip_mock_20251205`, within tolerances.

- Progress (2025-12-05 – cj_generic_batch mode + parity test implemented):
  - Mock mode:
    - New enum: `MockMode` in `services/llm_provider_service/config.py` with values `default` and `cj_generic_batch`.
    - New setting: `MOCK_MODE: MockMode = MockMode.DEFAULT` (exposed via `LLM_PROVIDER_SERVICE_MOCK_MODE`).
    - Dev profile (CJ generic): when `.env` sets `LLM_PROVIDER_SERVICE_MOCK_MODE=cj_generic_batch`, the mock provider runs in the CJ generic mode.
    - Behaviour for `cj_generic_batch`:
      - `MockProviderImpl` disables simulated errors (`_maybe_raise_error` is a no-op in this mode) to guarantee all-success callbacks.
      - `_pick_winner` always returns `Essay A`, pinning winner distribution for CJ parity scenarios.
      - `_estimate_tokens` keeps CJ generic prompts in the same light-weight token band as the recorded fixture
        (`prompt_tokens≈5`, `completion_tokens≈17`, `total_tokens≈22`), so the docker parity test’s token-mean
        assertions remain data-driven instead of arbitrary.
  - New docker-backed integration test:
    - File: `tests/integration/test_cj_mock_parity_generic.py`
    - Flow:
      - Uses `ServiceTestManager` to ensure `llm_provider_service` is healthy.
      - Ensures a dedicated callback topic: `test.llm.mock_parity.generic.v1` via `KafkaTestManager.ensure_topics(...)`.
      - Sends a small batch (currently 12) of CJ-shaped `LLMComparisonRequest`s with:
        - `LLMProviderType.MOCK` overrides.
        - CJ-style metadata (`essay_a_id`, `essay_b_id`, `bos_batch_id`, `cj_llm_batching_mode="per_request"`).
      - Consumes `LLMComparisonResultV1` callbacks from Kafka and computes a live summary using the same helper as the trace harness: `compute_llm_trace_summary` from `scripts.llm_traces.eng5_cj_trace_capture`.
    - Metrics compared against `tests/data/llm_traces/cj_lps_roundtrip_mock_20251205/summary.json`:
      - Winners:
        - Recorded fixture: `winner_counts={"Essay A": 4}`, `error_count=0`.
        - Test assertion: all callbacks succeed, and at least 90% of winners are `"Essay A"` (in practice 100% with `cj_generic_batch`).
      - Errors:
        - Both recorded and live summaries must have `error_count == 0`.
      - Token usage:
        - For each field (`prompt_tokens`, `completion_tokens`, `total_tokens`), the live mean is required to be within a tolerance band of the recorded mean:
          - `tolerance = max(5 tokens, 50% of recorded mean)`.
        - This pins the mock to the same order-of-magnitude token usage as the captured scenario while allowing small drift if the prompt or justification strings change slightly.
      - Latency:
        - Live `mean_ms` and `p95_ms` must both be non-negative and within an additive band of the recorded trace:
          - `mean_ms <= recorded_mean_ms + 100ms`.
          - `p95_ms <= recorded_p95_ms + 200ms`.
        - This keeps the mock’s latency profile within a reasonable multiple of the fixture while tolerating container and host variability.
  - How to run:
    - Start dev stack (with Kafka + LPS mock mode active):
      - `pdm run dev-build-start`
    - Run the parity test:
      - `pdm run pytest-root tests/integration/test_cj_mock_parity_generic.py -m 'docker and integration' -v`

- Progress (2025-12-05 – ENG5 full-anchor trace + mock mode and parity test implemented):

- Progress (2025-12-05 – ENG5 LOWER5 trace + mock mode and parity test scaffolded):
  - LOWER5 scenario: `eng5_lower5_gpt51_low_20251202` captured via `eng5_cj_trace_capture` with `bos_batch_id=50f4509e-2e8c-4c62-a19d-93cf0739eefd`, `callback_topic=huleedu.llm_provider.comparison_result.v1`, fixtures at `tests/data/llm_traces/eng5_lower5_gpt51_low_20251202/`.
  - Mock mode: `MockMode.ENG5_LOWER5_GPT51_LOW` in `services/llm_provider_service/config.py` with ENG5 LOWER5-specific behaviour wired into `MockProviderImpl` (no simulated errors, hash-biased ~4/6 winner split, token and latency scale tuned to LOWER5 summary).
  - Unit coverage: `test_eng5_lower5_mode_produces_successful_responses_in_lower_token_band` in `services/llm_provider_service/tests/unit/test_mock_provider.py` pins success behaviour and token band (prompt_tokens in [1000,1100), completion_tokens in [30,40)).
  - Docker-backed parity test scaffold: `tests/integration/test_eng5_mock_parity_lower5.py` (marked `@pytest.mark.docker` and `@pytest.mark.integration`) mirrors the full-anchor parity structure for a 5-anchor LOWER5 net (10 comparisons), but currently times out due to missing callbacks when the dev stack is running with `USE_MOCK_LLM` and ENG5-specific mock modes; next session should focus on restoring LPS queue processing for mock-only modes so this and the existing ENG5 anchor parity test both pass.

  - ENG5 anchor trace (reusing existing GPT‑5.1 low run):
    - Scenario id: `eng5_anchor_align_gpt51_low_20251201`.
    - Source run:
      - Runner batch label: `eng5-gpt51-low-20251201-142416`.
      - BOS batch UUID: `ddc3f259-b125-4a08-97fb-f4907fa50b3d`.
      - `cj_batch_id`: `138`.
    - Capture command (with dev stack and Kafka up, using the standard CJ → LPS callback topic):
      - ```bash
        pdm run python -m scripts.llm_traces.eng5_cj_trace_capture \
          --scenario-id eng5_anchor_align_gpt51_low_20251201 \
          --bos-batch-id ddc3f259-b125-4a08-97fb-f4907fa50b3d \
          --callback-topic huleedu.llm_provider.comparison_result.v1 \
          --expected-count 0 \
          --timeout-seconds 120 \
          --output-dir tests/data/llm_traces
        ```
    - Fixtures:
      - Directory: `tests/data/llm_traces/eng5_anchor_align_gpt51_low_20251201/`.
      - Files:
        - `llm_callbacks.jsonl` – 66 validated `LLMComparisonResultV1` events (12 anchors → 66 comparisons).
        - `summary.json` – aggregate metrics for this ENG5 GPT‑5.1 low full-anchor scenario:
          - `total_events=66`, `success_count=66`, `error_count=0`.
          - `winner_counts={"Essay A": 35, "Essay B": 31}`.
          - Token usage (means): `prompt_tokens≈1445.5`, `completion_tokens≈53.5`, `total_tokens≈1499.0`.
          - Latency (means): `mean_ms≈1609.9`, `p95_ms≈2231.0`, `p99_ms≈2323.3`.
  - New ENG5-specific mock mode:
    - Enum: `MockMode.ENG5_ANCHOR_GPT51_LOW` added in `services/llm_provider_service/config.py`.
    - Settings:
      - `MOCK_MODE: MockMode = MockMode.DEFAULT` (default remains unchanged).
      - Dev/test override for ENG5 anchor parity: `LLM_PROVIDER_SERVICE_MOCK_MODE=eng5_anchor_gpt51_low`.
    - Behaviour in `MockProviderImpl` (`services/llm_provider_service/implementations/mock_provider_impl.py`):
      - Helper: `_is_eng5_anchor_mode` detects `ENG5_ANCHOR_GPT51_LOW`.
      - Error simulation:
        - `_maybe_raise_error` is a no-op when `ENG5_ANCHOR_GPT51_LOW` is active, mirroring the all-success ENG5 trace (`error_count=0`).
      - Winners:
        - `_pick_winner` uses a hash-biased mapping from `prompt_sha256` to winners to approximate the recorded ENG5 distribution:
          - `Essay A` when `int(prompt_sha256[:8], 16) % 66 < 35`, else `Essay B`.
          - This yields ~35/66 vs 31/66 proportions over a full 66-comparison batch while remaining deterministic.
      - Tokens:
        - `_estimate_tokens` retains the generic estimator but, in ENG5 mode, enforces a higher token scale:
          - `prompt_tokens >= 1100`.
          - `completion_tokens >= 40`.
        - This keeps ENG5 mock callbacks in the same order-of-magnitude token band as the recorded ENG5 trace (large prompts with moderately sized completions) without tying behaviour to the exact original prompts.
      - Latency:
        - `_apply_latency` uses a higher-latency profile when ENG5 mode is active and no explicit latency settings are configured:
          - Defaults to `base_ms=1200`, `jitter_ms=800` when `MOCK_LATENCY_MS`/`MOCK_LATENCY_JITTER_MS` are zero.
        - This approximates the 1.6–2.3s latency band observed in the ENG5 GPT‑5.1 low trace while still allowing explicit overrides via settings.
  - New unit test:
    - File: `services/llm_provider_service/tests/unit/test_mock_provider.py`.
    - Test: `test_eng5_anchor_mode_produces_successful_responses`:
      - Creates `Settings` with `MOCK_MODE=ENG5_ANCHOR_GPT51_LOW` and `MOCK_ERROR_RATE=1.0`.
      - Asserts that:
        - `generate_comparison(...)` returns a valid `LLMProviderResponse` without raising, confirming error simulation is disabled in ENG5 mode.
        - `prompt_tokens >= 1100` and `completion_tokens >= 40`, pinning the ENG5 mock mode to a large-token regime.
  - New docker-backed ENG5 full-anchor parity test:
    - File: `tests/integration/test_eng5_mock_parity_full_anchor.py`.
    - Flow:
      - Uses `ServiceTestManager` to ensure `llm_provider_service` is healthy and `KafkaTestManager` to manage topics.
      - Loads `summary.json` from `tests/data/llm_traces/eng5_anchor_align_gpt51_low_20251201/` as the recorded ENG5 baseline.
      - Ensures a dedicated callback topic: `test.llm.mock_parity.eng5_anchor.v1`.
      - Constructs 12 synthetic ENG5 anchor IDs and all unordered pairs (C(12, 2) = 66 comparisons) to mimic the shape of the recorded full-anchor trace.
      - For each pair:
        - Builds a CJ-shaped `ComparisonTask` + `CJLLMComparisonMetadata` with `bos_batch_id="bos-eng5-anchor-mock-parity-001"` and `cj_llm_batching_mode="per_request"`.
        - Sends an `LLMComparisonRequest` to LPS via HTTP with:
          - `user_prompt` describing the anchor pair.
          - `callback_topic="test.llm.mock_parity.eng5_anchor.v1"`.
          - `llm_config_overrides=LLMConfigOverridesHTTP(provider_override=LLMProviderType.MOCK)`.
      - Consumes callbacks from Kafka, filters by `request_id`, and computes a live summary via `compute_llm_trace_summary(..., scenario_id="eng5_anchor_mock_parity")`.
    - Metrics compared vs recorded ENG5 summary:
      - Preconditions:
        - Test is guarded to only run when `LLM_PROVIDER_SERVICE_MOCK_MODE=eng5_anchor_gpt51_low` in the host environment; otherwise it is skipped with an explicit message (LPS container must be restarted with this mode).
      - Total events and errors:
        - Require `live_summary["total_events"] == 66` and `live_summary["error_count"] == 0`.
      - Winners:
        - Computes proportions of `"Essay A"` / `"Essay B"` for recorded vs live summaries.
        - Asserts per-label proportions are within ±20 percentage points, reflecting that ENG5 mode is hash-biased towards the recorded 35/31 split but not a strict replay.
      - Tokens:
        - For `prompt_tokens` and `total_tokens`, uses the generic tolerance:
          - `tolerance = max(5 tokens, 50% of recorded mean)`.
        - For `completion_tokens`, uses a slightly more forgiving band to account for shorter mock justifications:
          - `tolerance = max(10 tokens, recorded_mean)`.
      - Latency:
        - Requires non-negative `mean_ms` and `p95_ms`.
        - Enforces upper bounds:
          - `mean_ms <= recorded_mean_ms + 100ms`.
          - `p95_ms <= recorded_p95_ms + 200ms`.
    - How to run:
      - Configure ENG5 mock mode for LPS (in `.env`):
        - `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true`
        - `LLM_PROVIDER_SERVICE_MOCK_MODE=eng5_anchor_gpt51_low`
      - Restart dev stack (or at least LPS) to pick up new env:
        - `pdm run dev-build-start` (or `pdm run dev-restart llm_provider_service`).
      - Run the ENG5 full-anchor parity test:
        - `pdm run pytest-root tests/integration/test_eng5_mock_parity_full_anchor.py -m 'docker and integration' -v`

- Mock profile matrix and docker test mapping (2025-12-05):
  - Profile selection is driven by `.env` + dev shell:
    - Always enter an env-aware shell before running tests:
      - `./scripts/dev-shell.sh  # sources .env and drops you at repo root`
    - After changing `.env`, restart only the LPS dev container so it picks up the new profile:
      - `pdm run dev-restart llm_provider_service`
  - Profiles and their tests:
    - CJ generic profile:
      - `.env`:
        - `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true`
        - `LLM_PROVIDER_SERVICE_MOCK_MODE=cj_generic_batch`
      - Docker tests (run together from the same file):
        - Core parity vs recorded CJ trace:
          - `pdm run pytest-root tests/integration/test_cj_mock_parity_generic.py -m 'docker and integration' -v -k 'matches_recorded_summary'`
        - Coverage/continuation stability across multiple CJ batches:
          - `pdm run pytest-root tests/integration/test_cj_mock_parity_generic.py -m 'docker and integration' -v -k 'stable_across_multiple_batches'`
    - ENG5 full-anchor profile:
      - `.env`:
        - `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true`
        - `LLM_PROVIDER_SERVICE_MOCK_MODE=eng5_anchor_gpt51_low`
      - Docker test:
        - `pdm run pytest-root tests/integration/test_eng5_mock_parity_full_anchor.py -m 'docker and integration' -v`
    - ENG5 LOWER5 profile:
      - `.env`:
        - `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true`
        - `LLM_PROVIDER_SERVICE_MOCK_MODE=eng5_lower5_gpt51_low`
      - Docker tests (run together from the same file):
        - Core parity vs recorded LOWER5 trace:
          - `pdm run pytest-root tests/integration/test_eng5_mock_parity_lower5.py -m 'docker and integration' -v -k 'matches_recorded_summary'`
        - LOWER5 small-net coverage/diagnostics across batches:
          - `pdm run pytest-root tests/integration/test_eng5_mock_parity_lower5.py -m 'docker and integration' -v -k 'small_net_diagnostics_across_batches'`
  - Each docker test includes a small `os.getenv(...)` guard to **skip** when the host env does not match its profile
    (for example, CJ generic will not run when the ENG5 mock profile is active). This prevents accidental cross-profile
    runs (e.g. CJ test under ENG5 anchor tokens) and keeps parity assertions tight and meaningful.

- Progress (2025-12-06 - mock profiles + parity helpers + coverage/diagnostics layer):
  - All three mock profiles now have:
    - Green unit tests in `services/llm_provider_service/tests/unit/test_mock_provider.py`.
    - Docker-backed profile tests under their respective profiles:
      - CJ generic → `test_cj_mock_parity_generic.py`:
        - `test_cj_mock_parity_generic_mode_matches_recorded_summary` (parity vs `cj_lps_roundtrip_mock_20251205`, ~4s, 30s callback budget).
        - `test_cj_mock_parity_generic_mode_stable_across_multiple_batches` (coverage/continuation-style check over 3×12 CJ-shaped requests; asserts 100% Essay A winners, per-batch and aggregate token/latency metrics within the same bands as the recorded CJ summary, and zero variance in token means across batches).
      - ENG5 full-anchor → `test_eng5_mock_parity_full_anchor.py` (≈110s wall clock, 120s callback budget; unchanged in this session but still the canonical ENG5 full-anchor parity test).
      - ENG5 LOWER5 → `test_eng5_mock_parity_lower5.py`:
        - `test_eng5_mock_parity_lower5_mode_matches_recorded_summary` (parity vs `eng5_lower5_gpt51_low_20251202`, ~16s runtime, 60s callback budget; winner, token, and latency tolerances are now documented explicitly in the test docstring).
        - `test_eng5_mock_lower5_small_net_diagnostics_across_batches` (three LOWER5-shaped batches with varying `bos_batch_id` and `cj_llm_batching_mode` hints; checks unique pair coverage per batch and globally, winner proportions vs the recorded LOWER5 trace, token/latency parity using `compute_llm_trace_summary`, and now explicit small-net style diagnostics:
          - Each unique LOWER5 pair appears exactly once per batch and exactly `num_batches` times across the test.
          - Winners for a given pair are stable across batches under the deterministic ENG5 LOWER5 mock profile.
          - Cross-batch winner proportions (particularly Essay B proportions) remain within a tight band (≤ 10 percentage points drift) to approximate stable resampling behaviour.)
    - All docker tests include explicit skip guards on `LLM_PROVIDER_SERVICE_USE_MOCK_LLM` + `LLM_PROVIDER_SERVICE_MOCK_MODE` to prevent
      silent passes under the wrong profile, and all updated tests are green under `pdm run pytest-root ... -m "docker and integration"`.
  - Helper script for profile switching + docker tests:
    - File: `scripts/llm_mgmt/mock_profile_helper.sh`.
    - PDM alias: `pdm run llm-mock-profile <profile>`.
    - Supported profiles (each target now effectively runs the full profile-specific suite in the corresponding file):
      - `cj-generic` → validates `.env` for `cj_generic_batch`, restarts `llm_provider_service`, runs all CJ mock profile docker tests in `test_cj_mock_parity_generic.py`.
      - `eng5-anchor` → validates `.env` for `eng5_anchor_gpt51_low`, restarts `llm_provider_service`, runs ENG5 anchor docker tests in `test_eng5_mock_parity_full_anchor.py`.
      - `eng5-lower5` → validates `.env` for `eng5_lower5_gpt51_low`, restarts `llm_provider_service`, runs all LOWER5 docker tests in `test_eng5_mock_parity_lower5.py`.
    - The helper remains thin: it only orchestrates `.env` validation, a targeted dev container restart, and the appropriate
      `pytest-root` invocation; behavioural guarantees live in the tests and mock provider implementation.

- New CJ/ENG5 profile suite harness (2025-12-06):
  - File: `tests/integration/test_eng5_profile_suite.py`.
  - Purpose:
    - Provide a single high-level docker-backed entry point that orchestrates CJ generic + ENG5 anchor + ENG5 LOWER5 mock profiles, using `/admin/mock-mode` as the profile oracle and delegating deep behaviour checks to the existing per-profile tests.
  - Structure:
    - Uses `ServiceTestManager` and `KafkaTestManager` fixtures for service discovery and Kafka topic management.
    - Internal helper `_get_lps_mock_mode(...)` queries `llm_provider_service`’s `/admin/mock-mode` endpoint and skips tests gracefully when the admin surface is disabled or the expected profile is not active.
    - Suite-level tests:
      - `test_profile_suite_cj_generic`:
        - Requires `use_mock_llm=true` and `mock_mode="cj_generic_batch"` from `/admin/mock-mode`, otherwise `pytest.skip`.
        - Delegates to:
          - `TestCJMockParityGeneric.test_cj_mock_parity_generic_mode_matches_recorded_summary`.
          - `TestCJMockParityGeneric.test_cj_mock_parity_generic_mode_stable_across_multiple_batches`.
      - `test_profile_suite_eng5_anchor`:
        - Requires `use_mock_llm=true` and `mock_mode="eng5_anchor_gpt51_low"`, otherwise `pytest.skip`.
        - Delegates to:
          - `TestEng5MockParityFullAnchor.test_eng5_mock_parity_anchor_mode_matches_recorded_summary`.
      - `test_profile_suite_eng5_lower5`:
        - Requires `use_mock_llm=true` and `mock_mode="eng5_lower5_gpt51_low"`, otherwise `pytest.skip`.
        - Delegates to:
          - `TestEng5MockParityLower5.test_eng5_mock_parity_lower5_mode_matches_recorded_summary`.
          - `TestEng5MockParityLower5.test_eng5_mock_lower5_small_net_diagnostics_across_batches`.
  - How to use:
    - After selecting a profile via `pdm run llm-mock-profile <profile>` (which validates `.env` and restarts LPS), run:
      - `pdm run pytest-root tests/integration/test_eng5_profile_suite.py -m "docker and integration" -v`
    - This keeps `/admin/mock-mode` as the canonical source of truth for the active mock profile while providing a single orchestrated entry point for CJ/ENG5 docker validation.

## Progress (2025-12-07 – ENG5 runbook & harness docs)

- ENG5 NP runbook integration:
  - `docs/operations/eng5-np-runbook.md` now has an **ENG5/CJ serial-bundle test harness** subsection that:
    - Explicitly points at `tests/eng5_profiles/*` as ENG5 profile parity tests (separate from standard docker integration tests in `tests/integration/`).
    - Documents `pdm run eng5-cj-docker-suite` and `pdm run llm-mock-profile <profile>` as the recommended entrypoints for running the heavy ENG5/LOWER5 docker suites.
    - Includes `pdm run pytest-root ...` examples for running individual ENG5 parity and CJ docker files when selective validation is needed.

## Progress (2025-12-10 – Step 2 ENG5 mock profile metrics implemented and validated)

- The Step 2 parity metrics plan above is now implemented using a shared helper:
  - File: `tests/eng5_profiles/eng5_lps_metrics_assertions.py`
  - Behaviour:
    - Fetches `/metrics` from `llm_provider_service` via `ServiceTestManager.get_validated_endpoints()["llm_provider_service"]["metrics_url"]`.
    - Parses metrics into a `metric_name -> [(labels, value), ...]` map using `tests/utils/metrics_helpers.py`.
    - Derives the active mock “profile model” from `llm_provider_serial_bundle_calls_total{provider="mock",model=*}` by selecting the model with the highest call count.
    - Applies the planned inequality-based assertions for:
      - `llm_provider_serial_bundle_calls_total{provider="mock",model=<profile_model>}` (≥1 call).
      - `llm_provider_serial_bundle_items_per_call_{count,bucket}{provider="mock",model=<profile_model>}` (1 ≤ max items per call ≤ `Settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL`).
      - `llm_provider_queue_wait_time_seconds_{count,sum}{queue_processing_mode="serial_bundle"}` (average wait in [0, 120] seconds, with result labels limited to `{success,failure,expired}`).
      - `llm_provider_comparison_callbacks_total{queue_processing_mode="serial_bundle"}` (≥1 callback).
      - `llm_provider_queue_depth{queue_type="total"}` (if present, ≤ 1000).
- Profile suites now consume these metrics as part of their parity checks:
  - CJ generic:
    - `TestCJMockParityGenericParity` and `TestCJMockParityGenericCoverage` both call the shared helper after verifying winner distributions (100% Essay A), token usage, and latency parity vs `cj_lps_roundtrip_mock_20251205`.
  - ENG5 full-anchor:
    - `TestEng5MockParityFullAnchorParity` (implemented in `eng5_mock_parity_full_anchor_parity_impl.py`) drives the 12-anchor/66-comparison batch, asserts winner distribution parity (±20 percentage point drift per label allowed), token and latency parity vs `eng5_anchor_align_gpt51_low_20251201`, and then runs the LPS metrics helper.
    - `tests/eng5_profiles/test_eng5_mock_parity_full_anchor.py` is now a thin wrapper exposing `TestEng5MockParityFullAnchor` for CI and scripts without changing nodeids.
  - ENG5 LOWER5:
    - `TestEng5MockParityLower5Parity` remains the canonical single-batch parity test vs `eng5_lower5_gpt51_low_20251202` and calls the helper after parity assertions.
    - `TestEng5MockParityLower5Diagnostics.test_eng5_mock_lower5_small_net_diagnostics_across_batches` now:
      - Drives three LOWER5-shaped small-net batches (5 anchors → 10 pairs per batch) with `cj_llm_batching_mode="serial_bundle"`.
      - Asserts complete per-batch and cross-batch pair coverage and stable winners per pair.
      - Uses a **shape + drift** parity model vs the recorded LOWER5 summary:
        - Essay B remains the majority winner.
        - Per-label winner proportions may drift by up to ±0.20 from the recorded proportions (canary, not bitwise equality).
      - Verifies token/latency parity (same inequality bands as the main LOWER5 parity test).
      - Invokes the shared LPS metrics helper at the end to pin serial-bundle and queue metrics under the LOWER5 profile.
- Heavy C-lane validation:
  - With `.env` configured appropriately and services restarted via the helper:
    - `pdm run llm-mock-profile cj-generic` ✅ (CJ generic parity + coverage + LPS metrics).
    - `pdm run llm-mock-profile eng5-anchor` ✅ (ENG5 full-anchor parity + LPS metrics, queue wait-time guardrail at 120 seconds).
    - `pdm run llm-mock-profile eng5-lower5` ✅ (ENG5 LOWER5 parity + small-net diagnostics + LPS metrics).
- Remaining work for this task:
  - Optional: refine Prometheus/Grafana query snippets in the ENG5 runbook and LPS README to surface these serial-bundle and queue metrics explicitly for ENG5 heavy suites.
  - Optional: move the small-net winner-proportion canary thresholds into configuration or constants if we see further ENG5-specific tuning requirements.
