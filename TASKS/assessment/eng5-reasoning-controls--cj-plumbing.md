---
id: 'eng5-reasoning-controls--cj-plumbing'
title: 'ENG5 reasoning controls & CJ plumbing'
type: 'task'
status: 'in_progress'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-02'
last_updated: '2025-12-02'
related: []
labels: []
---
# ENG5 reasoning controls & CJ plumbing

## Objective

Ensure ENG5 anchor-align runs using GPT‑5.1 respect the configured
`reasoning_effort` and `output_verbosity` settings end-to-end by correctly
threading ENG5 overrides through CJ into LLM Provider Service (LPS) and, for
OpenAI, into the `reasoning` and `text.verbosity` blocks of the final API
payload. This story makes ENG5-internal expectations match external experiments
where reasoning controls are set explicitly.

## Context

ENG5 runner CLI already exposes:

- `--anchor-align-provider`
- `--anchor-align-model`
- `--anchor-align-reasoning-effort`
- `--anchor-align-output-verbosity`

and `AnchorAlignHandler` stores the effective `LLMConfigOverrides` on CJ
requests (and ultimately on `cj_batch_uploads.processing_metadata`).

However, current behaviour shows:

- CJ → LPS HTTP payloads include provider/model and system/rubric overrides,
  but **do not** include `reasoning_effort` / `output_verbosity` for ENG5
  guest flows.
- LPS `openai_provider_impl` only sets `reasoning` / `text.verbosity` fields
  when these overrides are present.
- Net result: ENG5 GPT‑5.1 runs inside CJ are using OpenAI’s internal default
  reasoning mode, even when ENG5 runner and program docs say “reasoning_effort
  = low/none” and “output_verbosity = low/medium/high”.

This explains discrepancies between external prompt experiments (where
reasoning controls are set explicitly) and CJ/ENG5 experiments (where they are
currently dropped).

## Progress (2025-12-02)

- CJ → LPS plumbing now threads `reasoning_effort` / `output_verbosity` from
  `LLMConfigOverrides` into `CJLLMComparisonMetadata` and onward to
  `LLMProviderServiceClient.generate_comparison` via `metadata_context`.
- `LLMProviderServiceClient` builds `LLMConfigOverridesHTTP` payloads that
  include reasoning/verbosity hints when present and validates against the
  shared `LLMComparisonRequest` HTTP contract.
- CJ integration tests (`test_llm_payload_construction_integration.py`) now
  cover ENG5-style overrides including reasoning/verbosity, and LPS
  cross-service tests (`test_cj_lps_metadata_roundtrip.py`) assert that
  reasoning/verbosity survive the HTTP → queue → Kafka callback cycle in
  `request_metadata`.
- CJ completion semantics have been updated so that `CJBatchState.total_budget`
  is seeded from `comparison_budget.max_pairs_requested` and
  `completion_denominator()` returns this budget (not `min(budget, nC2)`),
  with unit tests guarding small-net LOWER5 behaviour (`test_batch_state_tracking.py`,
  `test_completion_threshold.py`).

## Plan

- Confirm ENG5 override plumbing into CJ:
  - Trace `LLMConfigOverrides` from:
    - `scripts/cj_experiments_runners/eng5_np/cli.py`
    - `scripts/cj_experiments_runners/eng5_np/handlers/anchor_align_handler.py`
    - into `ELS_CJAssessmentRequestV1.llm_config_overrides` and
      `CJAssessmentRequest` inside CJ.
  - Verify that `reasoning_effort` and `output_verbosity` are present in
    `cj_batch_uploads.processing_metadata.original_request.llm_config_overrides`
    for ENG5 batches.
- Thread reasoning fields into CJ → LPS metadata:
  - In CJ LLM interaction / batch orchestration:
    - When building metadata for LPS requests (e.g.
      `LLMInteractionImpl.perform_comparisons` /
      `ComparisonBatchOrchestrator`), extract `reasoning_effort` and
      `output_verbosity` from `LLMConfigOverrides`.
    - Attach them to `CJLLMComparisonMetadata` / `request_metadata` so that
      `LLMProviderServiceClient` has access to them.
  - In `LLMProviderServiceClient`:
    - Ensure `_build_llm_config_override_payload(...)` includes
      `reasoning_effort` and `output_verbosity` when present, alongside
      provider/model/system/rubric overrides.
- Validate LPS/OpenAI behaviour:
  - Confirm in `services/llm_provider_service/implementations/openai_provider_impl.py`
    that:
    - `reasoning_effort` maps to `{"reasoning": {"effort": ...}}`.
    - `output_verbosity` maps to `{"text": {"verbosity": ...}}` for GPT‑5.x.
  - Extend/adjust existing tests:
    - `services/llm_provider_service/tests/unit/test_orchestrator_reasoning_overrides.py`.
    - `services/llm_provider_service/tests/unit/test_openai_provider_gpt5_family.py`.
  - Add a CJ-level unit test that:
    - Creates a synthetic comparison request with
      `llm_config_overrides.reasoning_effort="low"` and
      `output_verbosity="low"`.
    - Asserts that the CJ → LPS HTTP payload includes these fields.
- End-to-end verification with ENG5:
  - Run a small ENG5 anchor-align batch (LOWER5 or full anchors) with:
    - `reasoning_effort` set to `"low"` and `"none"` in separate runs.
  - Inspect:
    - CJ comparison metadata / LPS logs / debug payloads to confirm OpenAI
      sees `reasoning.effort` and `text.verbosity` as configured.
  - Record batch IDs, prompts, and reasoning settings in the ENG5 program
    task, along with any observed behavioural differences (e.g. tail stability
    under LOW vs NONE).

## Success Criteria

- [x] For ENG5 anchor-align batches, `cj_batch_uploads.processing_metadata.original_request.llm_config_overrides`
      reliably contains `reasoning_effort` and `output_verbosity` when set by
      the runner.
- [x] CJ → LPS HTTP payloads for these batches include:
      - `llm_config_overrides.reasoning_effort`
      - `llm_config_overrides.output_verbosity`
      along with provider/model/system/rubric overrides.
- [x] LPS OpenAI provider calls set:
      - `request_body["reasoning"]["effort"]` and
      - `request_body["text"]["verbosity"]`
      according to ENG5 settings for GPT‑5.x models.
- [x] Unit tests in both CJ and LPS protect this plumbing end-to-end.
- [ ] At least one ENG5 run per setting (`reasoning_effort="low"` vs `"none"`)
      is documented in the ENG5 program task with batch IDs and observed tail
      behaviour, and `.claude/work/session/handoff.md` is updated accordingly.

## Related

- `TASKS/assessment/cj-completion-semantics-v2--eng5--lower5.md`
- `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md`
- `docs/operations/eng5-np-runbook.md`
