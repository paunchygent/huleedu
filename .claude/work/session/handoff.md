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

## 🎯 ACTIVE WORK (2025-11-30)

### 1. PR‑3: BT Standard Error Diagnostics & Observability (IN PROGRESS)

- Status: Implementation and tests landed; still needs follow‑up usage and
  adoption in monitoring/ops.
- What’s done (see CJ code + EPIC‑005/006 docs for details):
  - `BT_STANDARD_ERROR_MAX = 2.0` defined and applied in
    `bt_inference.compute_bt_standard_errors`.
  - Batch‑level SE summary (mean/max/min, counts, coverage stats) threaded
    into `CJBatchState.processing_metadata["bt_se_summary"]`.
  - Grade projector now exposes cohort‑level SE summaries (all/anchors/students).
  - Unit + integration tests around SE capping and metadata are in place.
- Next‑session focus:
  - Ensure dashboards/alerts actually consume `bt_se_summary` and any derived
    quality flags (see EPIC‑005/006 and CJ runbook).
  - Confirm ENG5 runners use these fields only for diagnostics (no gating).

### 2. PR‑4: CJ Scoring Core Refactor (BT inference robustness) – AWAITING REVIEW

- Status: Implementation complete and tests green; needs focused code review
  and sign‑off.
- What changed (high level, see PR‑4/task docs for details):
  - Introduced `BTScoringResult` helper and refactored
    `record_comparisons_and_update_scores` to be single‑session, single‑commit.
  - BT math isolated in a pure helper; SE diagnostics reused from PR‑3.
- Next‑session focus:
  - Perform reviewer‑level pass on scoring refactor (locking, transaction
    boundaries, error propagation).
  - Once approved, merge and confirm no regressions in CJ integration tests.

### 3. ENG5 NP Runner Refactor & Prompt-Tuning Harness – ALIGNMENT REPORTING FIXED

-- Status: Handler architecture + tests + docs are in place; alignment reporting
  semantics for `anchor-align-test` have been brought in line with CJ’s definition
  of usable comparisons.
  - Reporting now filters `llm_comparisons` to `status == \"succeeded\"` before
    computing wins/losses, zero-win anchors, and inversions.
  - The per-anchor table now includes a **Source File** column that maps each
    CJ/anchor ID back to the original filename under
    `test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays`, so
    duplicate grades (e.g. two A, B, or F+ anchors) can be uniquely identified.
  - “Direct inversions” are now reported as **unique anchor pairs** where the lower
    expert-grade anchor beats the higher-grade anchor; event-level inversions remain
    visible in the raw artefact but are not double-counted in the headline metric.
  - Unit tests under
    `scripts/cj_experiments_runners/eng5_np/tests/unit/test_alignment_report.py`
    were extended to cover mixed succeeded/failed comparisons, unique-pair
    deduplication, and report-level metric filtering; the suite is passing.
  - Implications:
  - For future vt_2017 `anchor-align-test` runs (with non-zero ENG5-specific
    `llm_comparisons`), the ENG5 alignment report should match CJ’s per-anchor
    wins/losses and inversion semantics when cross-checked against
    `cj_comparison_pairs` / `cj_processed_essays`.
  - The misalignment that previously inflated direct inversions (e.g. 35 vs
    ~5 expected) should be resolved; remaining discrepancies, if any, will be
    due to prompt behavior rather than reporting bugs.
  - Next‑session focus:
  1. Use the existing vt_2017 `anchor-align-test` CJ batch in the CJ Assessment
     DB (no rerun) to reconstruct per-anchor wins/losses and inversion pairs
     directly from `cj_comparison_pairs` / `cj_processed_essays`, and confirm
     they match the ENG5 artefact + alignment report (which already filter to
     successful comparisons and expose Source File).
  2. Once the DB ↔ ENG5 cross-check is clean, treat the existing batch as the
     baseline and compare its metrics against Batch 108 targets
     (direct inversions ≤ 1, zero-win anchors = 0, Kendall’s tau ≥ 0.90), then
     update `TASKS/assessment/anchor-alignment-prompt-tuning-experiment.md`
     with those baseline numbers.
  3. Only when exploring new prompt variants incur new CJ cost; reuse the
     existing baseline batch for all subsequent prompt-tuning comparisons.
  4. Local comparison limiting is now allowed for anchor-align flows:
     `apply_comparison_limit` no longer requires anchors when `max_comparisons`
     is set, enabling `--max-comparisons` for `anchor-align-test` without
     impacting EXECUTE mode semantics. Tests in
     `scripts/tests/test_eng5_np_cli_validation.py` encode this behaviour.

### 4. LLM Provider Service – Request-Level Overrides Bug (FIXED, AWAITING ENG5 VERIFICATION)

- Status: Code fix and unit tests implemented; needs ENG5 Sonnet run to confirm operational behaviour and logs.
- Fix:
  - Updated `LLMOrchestratorImpl._queue_request` in
    `services/llm_provider_service/implementations/llm_orchestrator_impl.py` to
    construct an `LLMConfigOverridesHTTP` instance (including `provider_override`,
    `model_override`, `temperature_override`, `system_prompt_override`,
    `max_tokens_override`) and attach it to `LLMComparisonRequest.llm_config_overrides`
    when creating the queued request. The resolved provider is always persisted
    so queue processing uses the same provider CJ requested.
  - Added `test_orchestrator_persists_llm_config_overrides_on_queued_request` in
    `services/llm_provider_service/tests/unit/test_orchestrator.py` to assert
    that `_queue_request` persists overrides into
    `QueuedRequest.request_data.llm_config_overrides`.
  - Added `test_execute_request_uses_llm_config_overrides` in
    `services/llm_provider_service/tests/unit/test_queue_request_executor.py` to
    assert that `QueuedRequestExecutor` (via `SingleRequestStrategy`) forwards
    `provider_override`, `model_override`, temperature, system prompt and
    max-tokens overrides into `comparison_processor.process_comparison`.
- Next-session focus:
  - Run a cheap ENG5 `anchor-align-test` Sonnet verification batch:
    `pdm run eng5-np-run --mode anchor-align-test --batch-id anchor-align-003-sonnet-verify-fixed --await-completion --system-prompt scripts/cj_experiments_runners/eng5_np/prompts/system/003_language_control.txt --rubric scripts/cj_experiments_runners/eng5_np/prompts/rubric/003_language_control.txt --llm-provider anthropic --llm-model claude-sonnet-4-5-20250929 --max-comparisons 12`.
  - Confirm `.claude/research/data/eng5_np_2016/assessment_run.anchor-align-test.json`
    reports `"model": "claude-sonnet-4-5-20250929"` for all `llm_comparisons[*]`.
  - Confirm LPS logs (`docker logs huleedu_llm_provider_service --since 5m`) show
    Anthropic provider entries with `using_override=True` and `model_id` equal to
    the Sonnet model id.
**References**

- Task: `TASKS/assessment/anchor-alignment-prompt-tuning-experiment.md`
- Epic: `docs/product/epics/eng5-runner-refactor-and-prompt-tuning-epic.md`
- Runbook: `docs/operations/eng5-np-runbook.md`
- Design: `docs/architecture/eng5-np-runner-handler-architecture.md`
