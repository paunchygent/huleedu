---
id: 'llm-provider-openai-gpt-5x-reasoning-controls'
title: 'LLM Provider OpenAI GPT-5.x Reasoning Controls'
type: 'task'
status: 'in_progress'
priority: 'high'
domain: 'infrastructure'
service: 'llm_provider_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-01'
last_updated: '2025-12-02'
related: ['EPIC-008']
labels: ['llm-provider', 'openai', 'gpt5']
---
# LLM Provider OpenAI GPT-5.x Reasoning Controls

## Objective

Enable the LLM Provider Service to call OpenAI GPT-5.x models
(`gpt-5-2025-08-07`, `gpt-5-mini-2025-08-07`, `gpt-5-nano-2025-08-07`,
`gpt-5.1`) with manifest‑accurate parameter flags and optional reasoning
controls (`reasoning.effort`, `text.verbosity`) so that ENG5 and CJ
experiments can safely adopt GPT‑5.x without violating OpenAI API semantics.

## Context

- GPT‑5 family models do **not** support traditional sampling parameters
  (`temperature`, `top_p`, `logprobs`); they use dedicated reasoning and
  verbosity controls instead.
- Our manifest already contains GPT‑5.x entries but needs to be aligned with
  the latest OpenAI model card and used consistently by the OpenAI provider
  implementation.
- ENG5 anchor‑alignment experiments and future CJ prompt work (EPIC‑008) will
  require experimenting with GPT‑5.x reasoning effort levels and comparing
  alignment reports across configurations.

## Plan

1. Confirm GPT‑5.x model IDs and parameter rules via Context7 + OpenAI docs.
2. Lock in GPT‑5.x manifest entries and capability flags (no sampling params,
   `uses_max_completion_tokens=True`).
3. Extend `OpenAIProviderImpl` to accept internal reasoning/verbosity
   overrides and map them into OpenAI payloads for GPT‑5 family models.
4. Thread `reasoning_effort` / `output_verbosity` through LLM orchestrator
   overrides so internal callers can control GPT‑5.x behavior.
5. Extend `LLMConfigOverridesHTTP` and `LLMConfigOverrides` to carry
   reasoning/verbosity hints across service boundaries; update CJ’s LLM
   client to translate event overrides into HTTP payloads.
6. Add unit tests for manifest, provider payload construction, orchestrator
   plumbing, and CJ client override translation.

## Success Criteria

- GPT‑5.x manifest entries:
  - Share GPT‑5 family capability flags and parameter compatibility
    (`supports_temperature=False`, `uses_max_completion_tokens=True`).
  - Are covered by targeted unit tests.
- OpenAI provider:
  - Uses `max_completion_tokens` and omits `temperature` for GPT‑5.x models.
  - Maps `reasoning_effort` → `payload['reasoning']['effort']` for GPT‑5.x
    when provided.
  - Maps `output_verbosity` → `payload['text']['verbosity']` for GPT‑5.x
    when provided.
- Orchestrator:
  - Forwards `reasoning_effort` / `output_verbosity` overrides into provider
    calls; unit tests verify kwarg plumbing.
- CJ LLM client:
  - Translates `LLMConfigOverrides` (event) into `LLMConfigOverridesHTTP`
    including reasoning/verbosity when present.
  - Existing tests remain green and new tests cover mixed override sources.
- Quality gates:
  - `pdm run typecheck-all` is clean.
  - `pdm run format-all` and `pdm run lint-fix --unsafe-fixes` are clean.
  - Targeted pytest suites for manifest, provider, orchestrator, and CJ
    client all pass.

## Progress (2025-12-01)

- Locked GPT‑5 family manifest semantics in `services/llm_provider_service/manifest/openai.py` and added `test_openai_manifest_gpt5_family.py` to assert `model_family='gpt-5'`, sampling flags disabled, `uses_max_completion_tokens=True`, and required capabilities for `gpt-5-2025-08-07`, `gpt-5-mini-2025-08-07`, `gpt-5-nano-2025-08-07`, and `gpt-5.1`.
- Extended `OpenAIProviderImpl.generate_comparison` / `_make_api_request` to accept `reasoning_effort` / `output_verbosity` and, for GPT‑5 family models, emit `max_completion_tokens`, `reasoning={'effort': ...}`, and `text={'verbosity': ...}` while omitting `temperature`; validated via `test_openai_provider_gpt5_family.py`.
- Updated LLM orchestrator + queue plumbing so `LLMConfigOverridesHTTP.reasoning_effort` / `.output_verbosity` are preserved on queued requests and forwarded unchanged into provider calls (`llm_orchestrator_impl.py`, `llm_override_utils.py`), covered by `test_orchestrator_reasoning_overrides.py`.
- Confirmed CJ Assessment → LLM Provider HTTP client translates reasoning/verbosity overrides by extending `_build_llm_config_override_payload` tests in `services/cj_assessment_service/tests/unit/test_llm_provider_service_client.py` and re‑running the full client test suite.

## Progress (2025-12-02)

- CJ batch orchestration (`ComparisonBatchOrchestrator` + `BatchRetryProcessor`) now
  injects `reasoning_effort` / `output_verbosity` from `LLMConfigOverrides` into
  `CJLLMComparisonMetadata` so that ENG5-style overrides flow into
  `LLMComparisonRequest.metadata` and are consumed by `LLMProviderServiceClient`.
- New CJ unit/integration tests (`test_generate_comparison_builds_reasoning_overrides_from_metadata`,
  `TestLLMPayloadConstructionIntegration::test_eng5_overrides_reach_llm_provider`) and
  cross-service contract tests (`TestCJLPSMetadataRoundtrip::test_reasoning_overrides_roundtrip`)
  now guard the full ENG5 → CJ → LPS reasoning/verbosity path.

### Canonical GPT‑5.1 low configuration (ENG5 anchor-align)

- For ENG5 anchor-align experiments that target GPT‑5.1 via LLM Provider, we
  currently treat the following as the canonical OpenAI configuration:
  - Provider/model: `openai` / `gpt-5.1`
  - Reasoning effort: `"low"`
  - Output verbosity: `"low"`
- These settings are passed from ENG5 through `LLMConfigOverrides` and
  `LLMConfigOverridesHTTP` into the OpenAI provider payload as
  `reasoning.effort` and `text.verbosity` for GPT‑5 family models.

## Related

- Epic: `docs/product/epics/eng5-runner-refactor-and-prompt-tuning-epic.md` (EPIC‑008)
- Service: `services/llm_provider_service`
- OpenAI manifest: `services/llm_provider_service/manifest/openai.py`
- CJ client: `services/cj_assessment_service/implementations/llm_provider_service_client.py`
