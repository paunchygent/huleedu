---
id: 'cj-lps-reasoning-verbosity-metadata-contract'
title: 'CJ LPS reasoning-verbosity metadata contract'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'architecture'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-02'
last_updated: '2025-12-02'
related: []
labels: []
---
# CJ LPS reasoning-verbosity metadata contract

## Objective

Define and harden the cross-service contract for `reasoning_effort` and
`output_verbosity` overrides between CJ Assessment and LLM Provider Service
so that:

- ENG5 and future clients can rely on these overrides being preserved
  end-to-end via typed contracts (not ad-hoc JSON), and
- tests accurately detect any regression in this plumbing instead of giving
  false confidence.

## Context

We now support GPT‑5.x reasoning controls in LLM Provider Service:

- `LLMConfigOverridesHTTP` (common_core.api_models.llm_provider) has
  typed fields:
  - `reasoning_effort: Literal["none","low","medium","high"] | None`
  - `output_verbosity: Literal["low","medium","high"] | None`
- LPS orchestrator and OpenAI provider:
  - Forward `reasoning_effort` / `output_verbosity` into provider calls
    (`test_orchestrator_reasoning_overrides.py`).
  - Map them to OpenAI payload fields (`test_openai_provider_gpt5_family.py`).

CJ also has partial support:

- `common_core.events.cj_assessment_events.LLMConfigOverrides` includes
  the same reasoning/verbosity fields.
- `services/cj_assessment_service/implementations/llm_provider_service_client.py`
  exposes `_build_llm_config_override_payload(...)` and a unit test
  (`test_llm_provider_service_client.py::test_accepts_reasoning_and_verbosity_from_cj_overrides`)
  that verifies these fields are accepted when present on the overrides model.

However, recent ENG5 runs showed that:

- ENG5 runner writes `reasoning_effort` / `output_verbosity` into
  `cj_batch_uploads.processing_metadata.original_request.llm_config_overrides`.
- CJ’s HTTP requests to LPS did **not** include these fields in
  `llm_config_overrides`, and LPS therefore used OpenAI’s internal default
  reasoning mode.

Why tests didn’t catch this:

- LPS unit tests (`test_orchestrator_reasoning_overrides.py`,
  `test_openai_provider_gpt5_family.py`) only exercise the orchestrator and
  provider **once the overrides are already present**; they do not verify that
  CJ sets these fields.
- CJ’s `test_accepts_reasoning_and_verbosity_from_cj_overrides` asserts
  `_build_llm_config_override_payload` behaves correctly **if** the overrides
  object includes `reasoning_effort` / `output_verbosity`, but the ENG5 path
  never actually supplied these values to that adapter.
- `tests/integration/test_cj_lps_metadata_roundtrip.py` validates metadata
  round-trip (essay IDs, bos_batch_id, batching mode, `prompt_sha256`) but
  constructs `LLMComparisonRequest` with only provider and
  `system_prompt_override`—no reasoning/verbosity—so it cannot fail when those
  fields are missing.

Net effect: we have strong per-service tests but **no contract-level test** for
`reasoning_effort` / `output_verbosity` at the CJ↔LPS boundary, allowing this
regression to slip through.

## Plan

- Decide and document contract shape (prefer typed over ad-hoc JSON):
  - Use `LLMConfigOverridesHTTP` as the canonical place for
    `reasoning_effort` / `output_verbosity` on HTTP requests.
  - Optionally mirror them in `CJLLMComparisonMetadata` as first-class keys for
    observability/diagnostics (not required for LPS contract).
- Harden CJ → LPS override adapter:
  - Ensure `CJAssessmentRequest` / CJ internal models always map
    `LLMConfigOverrides.reasoning_effort` / `output_verbosity` into the
    `LLMConfigOverridesHTTP` passed to `_build_llm_config_override_payload`.
  - Ensure fallback from `request_metadata["reasoning_effort"]` /
    `"output_verbosity"` is correctly populated when we decide to carry these
    hints via metadata in addition to overrides.
- Add explicit contract tests:
  - Extend `tests/integration/test_cj_lps_metadata_roundtrip.py` or add a
    sibling test that:
    - Builds a `LLMComparisonRequest` with reasoning/verbosity set on
      `LLMConfigOverridesHTTP`.
    - Asserts that:
      - LPS receives these values and forwards them to the configured provider.
      - The resulting `LLMComparisonResultV1.request_metadata` either preserves
        them or explicitly drops them (documented).
  - Add a CJ-level unit/integration test that:
    - Starts from a CJ assessment request / ENG5-style request with reasoning
      overrides.
    - Verifies that the HTTP payload to LPS includes them in
      `llm_config_overrides`.
- Align ENG5/LPS docs and tasks:
  - Tie this contract into:
    - `TASKS/assessment/eng5-reasoning-controls--cj-plumbing.md`.
    - `TASKS/infrastructure/llm-provider-openai-gpt-5x-reasoning-controls.md`.
    - `docs/operations/eng5-np-runbook.md` and LPS runbook (if needed).
  - Make it explicit that “reasoning_effort / output_verbosity” are
    **contracted HTTP fields**, not incidental metadata keys.

## Success Criteria

- [ ] CJ→LPS HTTP requests always include `reasoning_effort` /
      `output_verbosity` in `llm_config_overrides` when set by upstream
      clients (ENG5 or others).
- [ ] At least one cross-service integration test explicitly asserts
      reasoning/verbosity presence in CJ→LPS payloads and, if applicable, in
      callback metadata, so regressions cannot slip through.
- [ ] CJ and LPS unit tests clearly separate responsibilities:
      - LPS tests: “Given overrides, provider payload is correct.”
      - CJ tests: “Given CJ/ENG5 overrides, HTTP payload to LPS is correct.”
- [ ] ENG5 reasoning experiments and docs no longer claim behaviour (e.g.
      `reasoning_effort="low"`) that is not backed by the actual contract
      implementation; instead, they rely on this hardened boundary.

## Related

- `libs/common_core/src/common_core/api_models/llm_provider.py`
  (`LLMConfigOverridesHTTP`)
- `services/cj_assessment_service/implementations/llm_provider_service_client.py`
- `services/llm_provider_service/implementations/llm_orchestrator_impl.py`
- `services/llm_provider_service/implementations/openai_provider_impl.py`
- `tests/integration/test_cj_lps_metadata_roundtrip.py`
- `services/llm_provider_service/tests/unit/test_orchestrator_reasoning_overrides.py`
- `services/llm_provider_service/tests/unit/test_openai_provider_gpt5_family.py`
- `services/cj_assessment_service/tests/unit/test_llm_provider_service_client.py`

## Success Criteria

[How do we know it's done?]

## Related

[List related tasks or docs]
