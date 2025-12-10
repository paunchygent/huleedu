---
id: cj-llm-provider-batch-api-mode
title: CJ LLM Provider Batch API Mode
type: task
status: research
priority: medium
domain: assessment
service: cj_assessment_service
owner_team: agents
owner: ''
program: ''
created: '2025-11-27'
last_updated: '2025-12-10'
related: ["docs/decisions/0004-llm-provider-batching-mode-selection.md", "docs/decisions/0015-cj-assessment-convergence-tuning-strategy.md", "docs/decisions/0017-cj-assessment-wave-submission-pattern.md", "docs/operations/cj-assessment-runbook.md", "docs/operations/eng5-np-runbook.md", "services/llm_provider_service/README.md", "TASKS/assessment/cj-llm-serial-bundle-validation-fixes.md", "TASKS/integrations/llm-provider-batch-api-phase-2.md"]
labels: []
---

# Task: CJ LLM Provider Batch API Mode (All-at-Once to Cap)

> **User Story (BOS / ENG5)**  
> As BOS/BCS and the ENG5 runner, I want CJ to support a **provider batch API mode** where all comparison pairs for a batch (up to a configured cap) are generated and dispatched **in a single wave**, so the LLM Provider can execute one batched call per provider/model and CJ can finalize after the callbacks arrive without iterative continuation.

## Objective

Design and implement a clean, minimal `provider_batch_api` mode in CJ Assessment that:

- Generates all comparison pairs for a batch up to the configured budget cap in **one wave**.
- Submits them with `LLM_BATCHING_MODE=provider_batch_api` so LLM Provider Service uses its true batch API path.
- Finalizes after the first callback iteration once callbacks hit the denominator/cap, **ignoring stability** for continuation (scores are computed once).
- Retains the existing serial-bundle semantics as the default path for most workloads, using budgets as caps and stability-based early stop.

This task is a follow-on to `TASKS/assessment/cj-llm-serial-bundle-validation-fixes.md` and must align with:

- `TASKS/integrations/llm-provider-batch-api-phase-2.md` (Phase‑2 cross-service batch API design and rollout plan; LPS work must complete first for true provider-native jobs).

- ADR-0004 (LLM Provider batching mode selection)
- ADR-0015 (CJ convergence tuning)
- ADR-0017 (wave-based submission pattern and `preferred_bundle_size` hints)
- CJ/ENG5 runbooks (`docs/operations/cj-assessment-runbook.md`, `docs/operations/eng5-np-runbook.md`)
- LLM Provider README (`services/llm_provider_service/README.md`) for the queue processing
  contract (`QUEUE_PROCESSING_MODE`, `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL` default 64, and how
  `preferred_bundle_size` is interpreted during serial bundling).

## PRs

### PR 1 – Persist Effective Batching Mode & Single-Wave Generation

**Goal:** Ensure the effective batching mode is persisted in CJ batch metadata and that `provider_batch_api` mode generates all pairs up to the budget cap in a single wave.

**Files (CJ):**
- `services/cj_assessment_service/cj_core_logic/comparison_batch_orchestrator.py`
- `services/cj_assessment_service/cj_core_logic/llm_batching.py`

**Plan:**
- In `ComparisonBatchOrchestrator.submit_initial_batch()`:
  - After resolving `effective_batching_mode = batching_service.resolve_effective_mode(...)`, include `"llm_batching_mode": effective_batching_mode.value` in the metadata passed to `merge_batch_processing_metadata(...)` so that `CJBatchState.processing_metadata` records the effective mode.
  - When calling `pair_generation.generate_comparison_tasks(...)`, dynamically choose `existing_pairs_threshold`:
    - If `effective_batching_mode is LLMBatchingMode.PROVIDER_BATCH_API`: use `normalized.max_pairs_cap` so all required pairs up to the cap are generated in a single wave.
    - Otherwise: continue to use `settings.COMPARISONS_PER_STABILITY_CHECK_ITERATION` (current behaviour).
  - Guardrail: reuse the existing budget resolution logic (normalization + `MAX_PAIRWISE_COMPARISONS`) as the **single source of truth** for `max_pairs_cap`, and add tests that prove no more than `max_pairs_cap` comparisons are generated even for very large nets when `provider_batch_api` is active.

**Tests:**
- New unit test in `services/cj_assessment_service/tests/unit/test_comparison_processing.py` (or a new dedicated test file for the orchestrator) to assert that:
  - In `provider_batch_api` effective mode, `generate_comparison_tasks` is invoked with `existing_pairs_threshold == max_pairs_cap`.
  - `merge_batch_processing_metadata` receives a payload that includes `"llm_batching_mode": "provider_batch_api"`.
- **Progress 2025-12-07:** Initial CJ → LPS batching metadata hints wired and covered:
  - Builder-level capping in `services/cj_assessment_service/tests/unit/test_llm_batching_config.py::test_includes_capped_preferred_bundle_size` (`preferred_bundle_size` capped at 64 when hints are enabled).
  - Initial wave metadata in `services/cj_assessment_service/tests/unit/test_llm_batching_metadata.py::test_submit_initial_batch_sets_preferred_bundle_size_to_wave_size` ensuring `preferred_bundle_size == len(comparison_tasks)` and `<= 64`.
  - Retry wave metadata in `services/cj_assessment_service/tests/unit/test_retry_logic.py::test_retry_batch_metadata_includes_capped_preferred_bundle_size` ensuring retry hints are capped at 64.
- **Progress 2025-12-10:** Effective batching mode is now persisted into batch processing metadata:
   - `comparison_batch_orchestrator._prepare_batch_state` writes `"llm_batching_mode": <effective_mode.value>` via `merge_batch_processing_metadata(...)`.
   - `services/cj_assessment_service/tests/unit/test_llm_batching_metadata.py` asserts:
     - Serial-bundle runs persist `"llm_batching_mode": "serial_bundle"`.
     - Provider-batch runs persist `"llm_batching_mode": "provider_batch_api"`.

### PR 2 – Provider-Batch Continuation Semantics (No Iterative Waves)

**Goal:** In `provider_batch_api` mode, finalize after the first callback iteration once the cap/denominator has been reached, and never request additional comparison waves regardless of stability.

**Files (CJ):**
- `services/cj_assessment_service/cj_core_logic/workflow_continuation.py`

**Plan:**
- Add a small helper `_resolve_batching_mode(metadata, settings) -> LLMBatchingMode` that:
  - Reads `metadata.get("llm_batching_mode")` from `CJBatchState.processing_metadata`.
  - Maps string values to `LLMBatchingMode`, falling back to `settings.LLM_BATCHING_MODE` when missing/invalid.
- In `trigger_existing_workflow_continuation(...)`:
  - After loading `metadata`, resolve `effective_mode = _resolve_batching_mode(metadata, settings)`.
  - Adjust `should_finalize` logic:
    - If `effective_mode is LLMBatchingMode.PROVIDER_BATCH_API`:
      - `should_finalize = callbacks_reached_cap or budget_exhausted` (ignore `stability_passed`).
    - Else:
      - Keep current stability-first behaviour:
        - `should_finalize = stability_passed or callbacks_reached_cap or budget_exhausted`.
  - Guard additional wave submission:
    - Only call `comparison_processing.request_additional_comparisons_for_batch(...)` when:
      - `effective_mode is not LLMBatchingMode.PROVIDER_BATCH_API`, and
      - `pairs_remaining > 0`.

**Tests:**
- Extend `services/cj_assessment_service/tests/unit/test_workflow_continuation_orchestration.py` with:
  - `test_trigger_continuation_provider_batch_api_finalizes_without_requesting_more`:
    - Batch state has `"llm_batching_mode": "provider_batch_api"`, callbacks at denominator/cap, and remaining budget > 0.
    - Assert `BatchFinalizer.finalize_scoring` is called and `request_additional_comparisons_for_batch` is not.
  - `test_trigger_continuation_provider_batch_api_ignores_stability_flag`:
    - Force `check_score_stability` to return a large delta above threshold; ensure `should_finalize` still triggers based only on cap/denominator for `provider_batch_api`, and no new wave is requested.
- **Progress 2025-12-10:** Continuation logic now:
  - Resolves `effective_batching_mode` from `processing_metadata["llm_batching_mode"]` (with settings fallback).
  - Guards both RESAMPLING and regular continuation so `comparison_processing.request_additional_comparisons_for_batch(...)` is never invoked when `effective_mode == LLMBatchingMode.PROVIDER_BATCH_API`.
  - Adds orchestration tests in `test_workflow_continuation_orchestration.py` covering:
    - Finalization under `provider_batch_api` caps without requesting more comparisons.
    - Skipping additional waves when `llm_batching_mode="provider_batch_api"` even if stability checks suggest more work.

### PR 3 – ENG5 Runner Integration Hook

**Goal:** Allow the ENG5 NP runner to opt into `provider_batch_api` mode via CLI configuration while continuing to treat `--max-comparisons` purely as a cap.

**Files (ENG5 runner):**
- `scripts/cj_experiments_runners/eng5_np/cli.py`
- `scripts/tests/test_eng5_np_runner.py`

**Plan:**
- Expose a CLI flag or config option (e.g. `--llm-batching-mode provider_batch_api`) that:
  - Sets `batch_config_overrides.llm_batching_mode_override = "provider_batch_api"` in the CJ event payload.
  - Continues to send `max_comparisons_override` based on `--max-comparisons` as a cap.
- Ensure that existing default behaviour remains `serial_bundle` when no override is provided.

**Tests:**
- Add/extend runner tests to confirm that:
  - Given `--max-comparisons 200 --llm-batching-mode provider_batch_api`, the emitted CJ event contains:
    - `max_comparisons_override = 200`.
    - `batch_config_overrides.llm_batching_mode_override = "provider_batch_api"`.

## Out of Scope

- LLM Provider Service internal batch API implementation (queue processor and HTTP client changes are governed by ADR-0004 and now tracked under `TASKS/integrations/llm-provider-batch-api-phase-2.md`).
- Changes to ENG5 artefact schemas beyond any metadata needed to report batching mode and effective caps.

## Validation

- Unit tests:
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_workflow_continuation.py`
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_comparison_processing.py -k provider_batch_api`
  - `pdm run pytest-root scripts/tests/test_eng5_np_runner.py -k batching`
- End-to-end smoke (after LPS side is ready):
  - ENG5 execute mode with `llm-batching-mode=provider_batch_api` and realistic `--max-comparisons`:
    - Confirm a single wave of comparisons is submitted from CJ.
    - Confirm LPS reports batch API metrics for the ENG5 provider/model pair.
    - Confirm CJ finalizes after the first callback iteration with no continuation waves scheduled.
