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
last_updated: '2025-12-04'
related: ['EPIC-005', 'EPIC-008', 'llm-provider-openai-gpt-5x-reasoning-controls', 'llm-provider-anthropic-thinking-controls', 'cj-small-net-coverage-and-continuation-docker-validation']
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
  - [ ] CJ settings (e.g. `USE_MOCK_LLM`, `MOCK_LLM_MODE`).
  - [ ] ENG5 runner configs used by the docker tests (so the runner can select the appropriate mock mode).

### 3. Add docker trace-replay parity tests

All tests in this section:
- MUST be docker-backed (no in-process mocks of CJ repositories or models).
- MAY use the mock provider; real-provider traces are used as fixtures, not live calls.

#### 3.1 CJ trace replay vs mock for generic batches

- [ ] Add an integration test module (e.g. `tests/integration/test_cj_mock_parity_generic.py`) that:
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

- [ ] Add an integration test module (e.g. `tests/integration/test_eng5_mock_parity_full_anchor.py`) that:
  - [ ] Uses recorded ENG5 anchor-align real traces to compute reference metrics (as in 3.1) for a full-anchor run.
  - [ ] Runs the same ENG5 configuration via `eng5-runner` with `provider=openai`/Anthropic + mock mode enabled (no live external LLM).
  - [ ] Asserts:
    - [ ] CJ coverage and BT metrics parity, as above.
    - [ ] ENG5 DB reports (alignment report) see similar tau/inversion patterns across the anchor set (tolerances defined in EPIC‑008 context).

#### 3.3 ENG5 LOWER5 parity (small nets)

- [ ] Add an integration test module (e.g. `tests/integration/test_eng5_mock_parity_lower5.py`) that:
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
  - [ ] `pdm run pytest-root tests/integration/test_cj_mock_parity_generic.py`
  - [ ] `pdm run pytest-root tests/integration/test_eng5_mock_parity_full_anchor.py`
  - [ ] `pdm run pytest-root tests/integration/test_eng5_mock_parity_lower5.py`
  - [ ] `pdm run pytest-root tests/integration/test_cj_mock_parity_errors.py`
  - [ ] `pdm run pytest-root tests/integration/test_llm_mock_schema_parity.py`
- [ ] Run repo-wide quality gates:
  - [ ] `pdm run format-all`
  - [ ] `pdm run lint-fix --unsafe-fixes`
  - [ ] `pdm run typecheck-all`

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
