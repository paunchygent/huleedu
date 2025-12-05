# HANDOFF: Current Session Context

## Purpose

This document contains ONLY current/next-session work. All completed tasks,
architectural decisions, and patterns live in:

- **README_FIRST.md** – Architectural overview, decisions, service status
- **Service READMEs** – Service-specific patterns, error handling, testing
- **.claude/rules/** – Implementation standards and requirements
- **docs/operations/** – Operational runbooks
- **TASKS/** – Detailed task documentation

Use this file to coordinate what the very next agent should focus on.

---

## 🎯 ACTIVE WORK (2025-12-05)

- EPIC-007 US-007.3 COMPLETE - creation scripts added:
  - `scripts/docs_mgmt/new_doc.py` - creates runbooks, ADRs, epics (`pdm run new-doc`)
  - `scripts/claude_mgmt/new_rule.py` - creates rule files (`pdm run new-rule`)
  - All management scripts refactored to module pattern (no sys.path bootstrap)
  - PDM scripts run as `python -m scripts.*` for clean imports
  - DecisionFrontmatter.id pattern fixed to `^ADR-\d{4}$` for consistency with EpicFrontmatter
  - Next: US-007.4 (Indexing Scripts) or US-007.5 (Unified Validation)

- ENG5 GPT‑5.1 usage/content parity experiments (006/007 prompts, reasoning_effort in {\"low\",\"none\"}) + LOWER5 tail-only loop:
      - Tasks:
        - `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md`
        - `TASKS/programs/eng5/eng5-runner-assumption-hardening.md`
      - Entry points:
        - `scripts/cj_experiments_runners/eng5_np/cli.py` (ANCHOR_ALIGN_TEST mode, GPT‑5.1 flags + overrides)
        - `scripts/cj_experiments_runners/eng5_np/handlers/anchor_align_handler.py`
        - `scripts/cj_experiments_runners/eng5_np/paths.py` (ENG5_ANCHOR_DIR_OVERRIDE handling)
        - `scripts/cj_experiments_runners/eng5_np/db_alignment_report.py`
        - `docker-compose.eng5-lower5.override.yml` (CJ small‑net tuning for LOWER5)
      - Current focus: ENG5 LOWER5 tail alignment, GPT‑5.1 `reasoning_effort` in {`"low"`, `"none"`}, comparing usage guard 007 + 006 rubric vs 006/006 parity prompts, with DB-based reports as the canonical surface for tau/inversion/justification analysis, **and** fixing remaining CJ/LPS plumbing gaps so reasoning controls and small-net budgets behave as configured. ADR-0020 (`docs/decisions/0020-cj-assessment-completion-semantics-v2.md`) now captures the agreed simplification of CJ completion semantics: `total_budget` as the single source of truth for completion denominators, with small-net coverage (`nC2`) handled explicitly via small-net metadata instead of clamping the denominator.
      - Focus (next sessions):
        - Maintain a repeatable LOWER5 loop over the 5 weakest anchors (`D‑`, `E+`, `E‑`, `F+`, `F+`) using:
          - CJ dev overrides set via env/config (no compose override): e.g. `CJ_ASSESSMENT_SERVICE_MAX_PAIRWISE_COMPARISONS=60`, `CJ_ASSESSMENT_SERVICE_MIN_COMPARISONS_FOR_STABILITY_CHECK=60`, `CJ_ASSESSMENT_SERVICE_MIN_RESAMPLING_NET_SIZE=10`, `CJ_ASSESSMENT_SERVICE_MAX_RESAMPLING_PASSES_FOR_SMALL_NET=10` in your `.env` or shell before starting the standard `docker-compose.yml:docker-compose.dev.yml` stack.
          - ENG5 runner LOWER5 wiring: `ENG5_ANCHOR_DIR_OVERRIDE` → `/app/test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays_5_lowest_grades`.
          - Prompts: system `007_usage_guard.txt`, rubric `006_usage_content_parity_rubric.txt`.
          - Model: `openai` / `gpt-5.1`, where we **expect** `reasoning_effort` / `output_verbosity` from ENG5 runner overrides to reach OpenAI.
        - Known CJ/LPS plumbing gaps to fix (highest priority for dev implementing next session):
          - ✅ RESOLVED (2025-12-02): CJ now threads `LLMConfigOverrides.reasoning_effort` / `output_verbosity` from ENG5 into `CJLLMComparisonMetadata` and on to `LLMConfigOverridesHTTP` in the CJ → LPS HTTP payload; cross-service tests (`TestCJLPSMetadataRoundtrip::test_reasoning_overrides_roundtrip`) and CJ integration tests guard this contract. OpenAI GPT‑5.x provider continues to honour these hints via `reasoning.effort` / `text.verbosity`.
          - ✅ RESOLVED (2025-12-02): CJ completion semantics for small-net LOWER5 batches now treat `total_budget` as the completion denominator (no `min(budget, nC2)` clamp). `CJBatchState._resolve_total_budget()` seeds `total_budget` from `comparison_budget.max_pairs_requested`, and `completion_denominator()` returns this budget for all nets. Unit tests (`test_batch_state_tracking.py::test_small_net_total_budget_uses_configured_comparison_budget`, `test_completion_threshold.py::test_completion_denominator_uses_small_batch_nc2_cap`) cover the new behaviour; ENG5 LOWER5 experiments still need to be run to confirm multi-wave resampling and >10 comparisons in practice.
          - ✅ RESOLVED (2025-12-04): CJ coverage helper and continuation tests have been refactored:
            - `PostgreSQLCJComparisonRepository.get_coverage_metrics_for_batch` now counts any unordered pair with a non-null, non-`"error"` winner as covered, ignores error-only pairs, and treats retry success as coverage (see `test_comparison_repository_coverage_metrics.py`).
            - Workflow continuation tests are split into SRP-aligned modules under `services/cj_assessment_service/tests/unit/` and all kept under the 500 LoC limit: `test_workflow_continuation_check.py`, `test_workflow_continuation_orchestration.py`, `test_workflow_continuation_success_rate.py`, `test_workflow_small_net_resampling.py`, and `test_workflow_continuation_metadata_bt_flags.py`.
        - After each run, generate DB-based LOWER5 reports via `scripts.cj_experiments_runners/eng5_np/db_alignment_report.py` with `--system-prompt-file 007_usage_guard.txt` and `--rubric-file 006_usage_content_parity_rubric.txt`, and capture:
          - Kendall’s tau over the 5‑essay ladder.
          - Direct inversions among {D‑, E+, E‑, F+, F+}.
          - Justification patterns, especially for “wrong” tail picks.
        - Keep `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md` updated with:
          - The canonical LOWER5 loop command.
          - Paths to the latest LOWER5 DB reports.
          - Notes on tail behaviour changes across runs (e.g. if usage guard tightens or loosens preference bias at F+/E‑ boundary).
        - Latest LOWER5 runs (2025-12-01/02, GPT‑5.1 low/low and none/low; all currently capped at 10 comparisons because of the denominator issue above):
          - 007 system + 006 rubric (usage guard + parity rubric):
          - Runner batch: `batch_id=eng5-gpt51-lower5-007-20251202-001714`, `batch_uuid=50f4509e-2e8c-4c62-a19d-93cf0739eefd`, `cj_batch_id=147`.
          - DB-based reports:
            - Summary: `.claude/research/data/eng5_np_2016/anchor_align_db_50f4509e-2e8c-4c62-a19d-93cf0739eefd_20251201_231822.md`
            - Full: `.claude/research/data/eng5_np_2016/anchor_align_db_full_50f4509e-2e8c-4c62-a19d-93cf0739eefd_20251201_231822.md`
          - Metrics: Kendall’s tau `= 1.000` over the 5‑essay ladder (`D‑ > E+ > E‑ > F+ > F+`), `0` direct inversions, and one zero‑win F+ anchor; CJ small‑net overrides yielded exactly 10 comparisons (full LOWER5 pair coverage).
          - Justification patterns: winners consistently described as having clearer structure, richer content, and fewer basic errors; no tail inversions (no F+ beating D‑/E±), suggesting usage guard 007 is not inducing pathological tail behaviour under LOWER5.
          - 006 system + 006 rubric (pure usage/content parity pair):
            - Runner batch: `batch_id=eng5-gpt51-lower5-006-20251202-002205`, `batch_uuid=ec9c935c-e589-448c-b829-56ad545862f5`, `cj_batch_id=148`.
            - DB-based reports:
              - Summary: `.claude/research/data/eng5_np_2016/anchor_align_db_ec9c935c-e589-448c-b829-56ad545862f5_20251201_232251.md`
              - Full: `.claude/research/data/eng5_np_2016/anchor_align_db_full_ec9c935c-e589-448c-b829-56ad545862f5_20251201_232251.md`
            - Metrics: Kendall’s tau `= 0.800`, `1` direct inversion where F+ `ANCHOR_ESSAY_ENG_5_363940D5` beats higher‑graded E‑ `ANCHOR_ESSAY_ENG_5_73127661` (justification: “Clearer structure, richer content”); one zero‑win F+ anchor (`D298E687`), with D‑ and E+ still ranked 1–2.
            - Interpretation: relative to 007+006, the 006/006 pair slightly relaxes the tail floor, allowing a structurally/content‑strong F+ to overtake E‑ in one comparison while preserving the top of the ladder.
          - Additional LOWER5 runs with `reasoning_effort="none"`:
            - 007 system + 006 rubric:
              - Runner batch: `batch_id=eng5-gpt51-lower5-007-none-20251202-003112`, `batch_uuid=4ce7468b-bf15-46b8-8a97-ebe51f79d45f`, `cj_batch_id=149`.
              - DB-based reports: `.claude/research/data/eng5_np_2016/anchor_align_db_4ce7468b-bf15-46b8-8a97-ebe51f79d45f_20251201_233151.md` (summary) and `.claude/research/data/eng5_np_2016/anchor_align_db_full_4ce7468b-bf15-46b8-8a97-ebe51f79d45f_20251201_233151.md` (full).
              - Metrics: Kendall’s tau `= 0.800`, `1` direct inversion where F+ `ANCHOR_ESSAY_ENG_5_D298E687` beats E‑ `ANCHOR_ESSAY_ENG_5_73127661` (justification: clearer structure, fuller ideas, slightly better basic control), one zero‑win F+ anchor; D‑ and E+ remain 1–2.
            - 006 system + 006 rubric:
              - Runner batch: `batch_id=eng5-gpt51-lower5-006-none-20251202-003200`, `batch_uuid=8cb7d51a-abc9-486c-bc4f-3654c19da7e1`, `cj_batch_id=150`.
              - DB-based reports: `.claude/research/data/eng5_np_2016/anchor_align_db_8cb7d51a-abc9-486c-bc4f-3654c19da7e1_20251201_233241.md` (summary) and `.claude/research/data/eng5_np_2016/anchor_align_db_full_8cb7d51a-abc9-486c-bc4f-3654c19da7e1_20251201_233241.md` (full).
              - Metrics: Kendall’s tau `= 1.000`, `0` direct inversions, one zero‑win F+ anchor with ladder `D‑ > E+ > E‑ > F+ > F+`, mirroring the low/low 007+006 run.
            - 009 system + 008 rubric (strong usage prompt + strong usage rubric), reasoning_effort=`"low"`:
              - Runner batch: `batch_id=eng5-gpt51-lower5-009-008-20251202-170737`, `batch_uuid=cfa94544-e80e-48e7-afa7-dff3e856b57d`, `cj_batch_id=155`.
              - DB-based reports: `.claude/research/data/eng5_np_2016/anchor_align_db_cfa94544-e80e-48e7-afa7-dff3e856b57d_20251202_170737.md` (summary) and `.claude/research/data/eng5_np_2016/anchor_align_db_full_cfa94544-e80e-48e7-afa7-dff3e856b57d_20251202_170737.md` (full).
              - Metrics: `Total comparisons = 10`, Kendall’s tau `≈ 0.600`, `2` direct inversions at the E‑/F+ boundary (both F+ essays beating E‑ with usage/structure‑focused justifications); further interpretation is blocked until reasoning controls + small‑net behaviour are fixed and the budget‑driven resampling path is exercised.
          - Suggested next experiments:
            - First, **fix plumbing** so ENG5 `reasoning_effort` / `output_verbosity` values reach LLM Provider, and adjust CJ completion logic so LOWER5 runs can actually use the configured 60‑comparison budget and `MAX_RESAMPLING_PASSES_FOR_SMALL_NET` without being hard‑capped at `C(n,2)`.
            - Then repeat LOWER5 for each (prompt, reasoning_effort) combination to estimate inversion frequency (especially F+/E‑ crossings) and stability now that reasoning controls and resampling are behaving as expected.
            - Consider a small grid over `output_verbosity` or budget (within safety constraints) if PM wants to probe whether richer justifications correlate with safer tail alignment under 006/006 once the above fixes land.

### Next sessions – concrete entry points

- Scope: Do **not** change CJ/LPS contracts or reasoning controls; focus on running and analysing ENG5 LOWER5 experiments now that CJ respects `total_budget` for small nets.
- Start with LOWER5 loops:
  - Commands: see canonical LOWER5 run in `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md` and `docs/operations/eng5-np-runbook.md`.
  - Files/tests: `docker-compose.eng5-lower5.override.yml`, `scripts/cj_experiments_runners/eng5_np/db_alignment_report.py`, `services/cj_assessment_service/tests/unit/test_batch_state_tracking.py`, `services/cj_assessment_service/tests/unit/test_completion_threshold.py`.
- Analyse LOWER5 reports:
  - Generate DB reports per run and capture tau/inversions/justifications for the 5 anchors; record findings back into `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md`.
- Optional future work (keep in TASKS, not this session):
  - Refine Anthropic thinking controls and logging (`services/llm_provider_service/implementations/anthropic_provider_impl.py`, `services/llm_provider_service/tests/integration/test_anthropic_prompt_cache_blocks.py`).
  - Design and implement Google Gemini `thinkingConfig` mapping driven by `reasoning_effort` (see `TASKS/infrastructure/llm-provider-anthropic-thinking-controls.md` for current thinking patterns).

- LLM mock provider CJ behavioural parity tests (trace capture harness + first generic scenario):
  - Task:
    - `TASKS/infrastructure/llm-mock-provider-cj-behavioural-parity-tests.md`
  - New tooling implemented this session:
    - Trace capture harness:
      - `scripts/llm_traces/eng5_cj_trace_capture.py`
        - Connects to Kafka, filters `LLMComparisonResultV1` callbacks by `request_metadata.bos_batch_id`, and persists:
          - Raw callbacks as JSONL fixtures.
          - Aggregate metrics summary (winner counts, error profile, response time stats, token usage stats; BT fields left as placeholders).
      - Unit test:
        - `scripts/tests/test_eng5_cj_trace_capture.py` – verifies summariser behaviour on synthetic callbacks.
    - First canonical trace for a generic CJ ↔ LPS path:
      - Scenario id: `cj_lps_roundtrip_mock_20251205`
      - Source flow:
        - `tests/integration/test_cj_lps_metadata_roundtrip.py::TestCJLPSMetadataRoundtrip::test_metadata_preserved_through_http_kafka_roundtrip`
        - Uses `callback_topic="test.llm.callback.roundtrip.v1"`, `bos_batch_id="bos-roundtrip-001"`, `LLMProviderType.MOCK`.
      - Fixtures:
        - Directory: `tests/data/llm_traces/cj_lps_roundtrip_mock_20251205/`
        - Files:
          - `llm_callbacks.jsonl` – 4 validated `LLMComparisonResultV1` callbacks.
          - `summary.json` – aggregate metrics for this scenario (all successes, `winner_counts={"Essay A": 4}`, no errors, stable token usage bands).
  - How to regenerate this scenario:
    - Ensure dev stack is running:
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
  - Latest progress on this stream (2025-12-05):
    - Mock mode:
      - New `MockMode` enum and `MOCK_MODE` setting added to `services/llm_provider_service/config.py` (`default` | `cj_generic_batch`).
      - `.env` now sets `LLM_PROVIDER_SERVICE_MOCK_MODE=cj_generic_batch`, so the dev stack runs LPS in the CJ generic mock mode by default when `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true`.
      - `MockProviderImpl` treats `cj_generic_batch` as:
        - Always-success (no simulated provider errors, regardless of `MOCK_ERROR_RATE`).
        - Winner pinned to `Essay A` (confidence still derived from existing base/jitter settings), keeping behaviour aligned with the `cj_lps_roundtrip_mock_20251205` fixture while preserving existing metadata and token estimation semantics.
    - New docker-backed parity test:
      - File: `tests/integration/test_cj_mock_parity_generic.py`
      - Behaviour:
        - Uses `ServiceTestManager` and `KafkaTestManager` to send a small batch (12) of CJ-shaped `LLMComparisonRequest`s through LPS with `LLMProviderType.MOCK` and `callback_topic="test.llm.mock_parity.generic.v1"`.
        - Consumes `LLMComparisonResultV1` callbacks from Kafka and computes a live summary via `compute_llm_trace_summary` from `scripts.llm_traces.eng5_cj_trace_capture`.
        - Compares live metrics against `tests/data/llm_traces/cj_lps_roundtrip_mock_20251205/summary.json`:
          - Winners: require all-success callbacks and ≥90% `"Essay A"` winners (currently 100% with `cj_generic_batch`).
          - Errors: require `error_count == 0` (mirrors fixture).
          - Token usage: live mean prompt/completion/total tokens must stay within `max(5 tokens, 50% of recorded mean)` of the recorded means.
          - Latency: live `mean_ms` and `p95_ms` must be non-negative and within `+100ms` and `+200ms` respectively of the recorded summary, bounding the mock’s latency profile while tolerating container variance.
      - How to run:
        - Ensure dev stack (including Kafka + LPS) is running:
          - `pdm run dev-build-start`
        - Run the parity test:
          - `pdm run pytest-root tests/integration/test_cj_mock_parity_generic.py -m 'docker and integration' -v`
      - Caveats:
        - Assumes `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true` and `LLM_PROVIDER_SERVICE_MOCK_MODE=cj_generic_batch` are in effect for the LPS container (set via `.env` + standard compose).
        - Generic parity test assumes `LLM_PROVIDER_SERVICE_MOCK_MODE=cj_generic_batch`; ENG5-specific mock modes and traces are handled separately (see ENG5 full-anchor parity notes below).
  - ENG5 full-anchor mock parity status (2025-12-05):
    - Trace:
      - Scenario id: `eng5_anchor_align_gpt51_low_20251201`.
      - Runner batch label: `eng5-gpt51-low-20251201-142416` (cj_batch_id `138`).
      - BOS batch UUID: `ddc3f259-b125-4a08-97fb-f4907fa50b3d`.
      - Callback topic used for capture: `huleedu.llm_provider.comparison_result.v1`.
      - Fixture path: `tests/data/llm_traces/eng5_anchor_align_gpt51_low_20251201/`.
    - Mock mode:
      - Name: `ENG5_ANCHOR_GPT51_LOW` in `services/llm_provider_service/config.py` (`MockMode` enum).
      - Behaviour (in `MockProviderImpl`):
        - `_is_eng5_anchor_mode` gates ENG5-specific behaviour.
        - `_maybe_raise_error` is disabled in ENG5 mode (all-success callbacks), matching the recorded ENG5 anchor trace.
        - `_pick_winner` uses a hash-biased mapping (`int(prompt_sha256[:8], 16) % 66 < 35`) to approximate the recorded 35/31 winner split for Essay A/B over a 66-comparison batch.
        - `_estimate_tokens` enforces a large-token regime for ENG5 mode (`prompt_tokens >= 1100`, `completion_tokens >= 40`) while still using the generic estimator as a base.
        - `_apply_latency` defaults to a higher-latency profile (`base_ms=1200`, `jitter_ms=800`) when no explicit mock latency is configured, approximating the 1.6–2.3s ENG5 latency band.
      - Env wiring:
        - Default dev stack remains `LLM_PROVIDER_SERVICE_MOCK_MODE=cj_generic_batch`.
        - ENG5 full-anchor parity test expects:
          - `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true`
          - `LLM_PROVIDER_SERVICE_MOCK_MODE=eng5_anchor_gpt51_low`
          - LPS restarted with those env vars applied.
    - Test:
      - File: `tests/integration/test_eng5_mock_parity_full_anchor.py`.
      - Pattern:
        - Uses `ServiceTestManager` and `KafkaTestManager` to validate services and create topic `test.llm.mock_parity.eng5_anchor.v1`.
        - Builds 12 synthetic ENG5 anchor IDs and all unordered pairs (C(12, 2) = 66) to mimic a full-anchor batch shape.
        - For each pair:
          - Constructs a CJ-shaped `ComparisonTask` / `CJLLMComparisonMetadata` with `bos_batch_id="bos-eng5-anchor-mock-parity-001"` and `cj_llm_batching_mode="per_request"`.
          - Sends an `LLMComparisonRequest` to LPS with `LLMProviderType.MOCK` override and the ENG5 parity callback topic.
        - Consumes `LLMComparisonResultV1` callbacks, filters by `request_id`, and computes a live summary via `compute_llm_trace_summary(..., scenario_id="eng5_anchor_mock_parity")`.
        - Compares live metrics against `summary.json` from the ENG5 trace fixture:
          - Requires 66/66 successes and `error_count == 0`.
          - Winner proportions for `"Essay A"` / `"Essay B"` must be within ±20 percentage points of the recorded 35/31 split.
          - Prompt/total token means must lie within `max(5 tokens, 50% of recorded mean)` of the recorded means.
          - Completion token means use a slightly more forgiving band (`tolerance = max(10 tokens, recorded_mean)`).
          - Latency mean and p95 must be non-negative and within `+100ms` / `+200ms` of the recorded ENG5 trace.
      - Run command (with ENG5 mock mode configured as above):
        - `pdm run pytest-root tests/integration/test_eng5_mock_parity_full_anchor.py -m 'docker and integration' -v`
      - Caveats:
        - The ENG5 full-anchor parity test is skipped unless `LLM_PROVIDER_SERVICE_MOCK_MODE=eng5_anchor_gpt51_low` is present in the test environment (matching the LPS container env).
        - Assumes the ENG5 GPT‑5.1 low full-anchor trace remains captured under `eng5_anchor_align_gpt51_low_20251201`; if storage is reset, re-run `eng5_cj_trace_capture` using the documented BOS batch id and callback topic.
  - Next recommended step for this stream (future session lead):
    - Extend parity from ENG5 full-anchor runs to ENG5 LOWER5 small-net runs, by:
      - Adding an ENG5 LOWER5-specific mock mode (e.g. `eng5_lower5_gpt51_low`) tuned against a LOWER5 GPT‑5.1 low trace (usage guard 007 + 006 rubric, 5 weakest anchors).
      - Capturing a LOWER5 trace fixture + `summary.json` into `tests/data/llm_traces/<eng5_lower5_scenario_id>/` using the same trace harness (`eng5_cj_trace_capture`) with the appropriate `bos_batch_id` and callback topic.
      - Adding a docker-backed integration test (e.g. `tests/integration/test_eng5_mock_parity_lower5.py`) that replays a LOWER5 CJ-shaped batch through LPS with the LOWER5 mock mode and compares winners, token usage, latency, and especially coverage / small-net metadata (Phase‑2 resampling and BT/coverage diagnostics) against the recorded LOWER5 fixture.

- Anthropic / thinking controls status (2025-12-02):
  - `AnthropicProviderImpl` now maps `reasoning_effort` to an Anthropic `thinking` block for models that advertise `extended_thinking` in the manifest (e.g. `claude-haiku-4-5-20251001`), with `budget_tokens` derived from `max_tokens` and clamped to the `[1024, max_tokens)` interval.
  - Non-thinking Anthropic models (or unknown model IDs) ignore `reasoning_effort` hints and do not emit a `thinking` payload, preserving existing behaviour.
  - Tests in `services/llm_provider_service/tests/integration/test_anthropic_prompt_cache_blocks.py` now pin down the `thinking` payload shape for thinking vs non-thinking models; Gemini `thinkingConfig` mapping remains design-only in `TASKS/infrastructure/llm-provider-anthropic-thinking-controls.md`.

---

## ✅ COMPLETED (2025-12-01)

- LLM Provider OpenAI GPT‑5.x reasoning controls:
  - GPT‑5 family manifest entries normalized with shared capability/parameter flags and covered by `test_openai_manifest_gpt5_family.py`.
  - `OpenAIProviderImpl` updated to send `max_completion_tokens` (no `temperature`) and, for GPT‑5 family models, map `reasoning_effort` and `output_verbosity` into `reasoning` / `text` controls; validated via `test_openai_provider_gpt5_family.py`.
  - Orchestrator + queue plumbing now preserve reasoning/verbosity overrides through `LLMConfigOverridesHTTP` and into provider calls (`test_orchestrator_reasoning_overrides.py`).
  - CJ LLM client override adapter tested to confirm reasoning/verbosity fields flow from `LLMConfigOverrides` / request metadata into LLM Provider HTTP payloads.
- ENG5 GPT‑5.1 anchor-align runner wiring and experiments (003 prompts):
  - ENG5 NP runner CLI/settings now expose anchor-align specific flags (`--anchor-align-provider`, `--anchor-align-model`, `--anchor-align-reasoning-effort`, `--anchor-align-output-verbosity`) and record effective values on `RunnerSettings`, while preserving Anthropic Haiku/Sonnet + 003 prompts as the default configuration.
  - `AnchorAlignHandler` augments existing `llm_overrides` with 003 system/rubric prompt text while preserving provider/model/temperature/max_tokens and the new `reasoning_effort` / `output_verbosity` fields so they reach `ELS_CJAssessmentRequestV1.llm_config_overrides` and, via CJ/LPS, the OpenAI HTTP payloads.
  - Three GPT‑5.1 anchor-align runs completed with 003 prompts and `output_verbosity="medium"`:
    - `eng5-gpt51-none-20251201-142319` (cj_batch_id 137, BOS UUID `05c687fc-463d-4c2d-bcaa-73250d0830ca`)
    - `eng5-gpt51-low-20251201-142416` (cj_batch_id 138, BOS UUID `ddc3f259-b125-4a08-97fb-f4907fa50b3d`)
    - `eng5-gpt51-medium-20251201-142646` (cj_batch_id 139, BOS UUID `7c0dcd60-deeb-482a-ad7c-f851df09f454`)
  - LLM Provider comparison callbacks for these batches confirm `provider="openai"`, `model="gpt-5.1"`, and `request_metadata.resolved_model="gpt-5.1"`; CJ now derives batch-level LLM attribution from `ComparisonPair.processing_metadata` so downstream `AssessmentResultV1` events can reflect OpenAI/GPT‑5.1 instead of legacy Anthropic defaults for these runs.
  - DB-based alignment reports (summary + full) have been generated for cj_batch_id 137–139 under `.claude/research/data/eng5_np_2016/anchor_align_db*_*.md`, providing complete comparison tables and justifications for reasoning-effort analysis. GPT‑5.1 `low` is the preferred reasoning setting for follow-up work, given comparable alignment and lower cost vs higher effort levels.

## ✅ COMPLETED (2025-11-30)

- Recent CJ work (PR‑2, PR‑3, PR‑4, PR‑7, US‑00XY/US‑00XZ/US‑00YA/US‑00YB) is fully documented in:
  - Task files under `TASKS/assessment/` and `TASKS/phase3_cj_confidence/`.
  - CJ epics and ADRs under `docs/product/epics/` and `docs/decisions/`.
  - CJ service README and runbook:
    - `services/cj_assessment_service/README.md`
    - `docs/operations/cj-assessment-runbook.md`
- ENG5 anchor-only alignment experiment completed:
  - Mode: `anchor-align-test`
  - Configuration: Anthropic `claude-sonnet-4-5-20250929` + 003 language-control system/rubric prompts.
  - Report: `.claude/research/data/eng5_np_2016/anchor_align_eng5-language-control-sonnet45_20251130_235510.md`
- For historical context or design rationale, prefer those documents rather than this handoff.
