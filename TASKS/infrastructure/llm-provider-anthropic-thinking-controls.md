---
id: llm-provider-anthropic-thinking-controls
title: LLM Provider Anthropic thinking controls
type: task
status: done
priority: medium
domain: infrastructure
service: ''
owner_team: agents
owner: ''
program: ''
created: '2025-12-02'
last_updated: '2026-02-01'
related: []
labels: []
---
# LLM Provider Anthropic thinking controls

## Objective

Enable the LLM Provider Service to call Anthropic “thinking” models with
explicit control over extended thinking configuration (`thinking` /
`budget_tokens`) wired from our generic `reasoning_effort` overrides, so that
CJ/ENG5 experiments can tune “thinking effort” in a predictable, contract-backed
way analogous to the GPT‑5.x reasoning controls.

## Context

We have already:

- Introduced `reasoning_effort` / `output_verbosity` on the shared
  `LLMConfigOverridesHTTP` model (common_core).
- Implemented OpenAI GPT‑5.x reasoning controls in `OpenAIProviderImpl`, using
  `reasoning.effort` and `text.verbosity` payload fields (see
  `TASKS/infrastructure/llm-provider-openai-gpt-5x-reasoning-controls.md`).
- Begun hardening CJ↔LPS contracts for these overrides via
  `TASKS/architecture/cj-lps-reasoning-verbosity-metadata-contract.md`.

For Anthropic:

- `AnthropicProviderImpl.generate_comparison(...)` accepts
  `reasoning_effort` / `output_verbosity` in its signature but currently
  ignores these parameters when building the payload.
- Claude API now exposes explicit extended thinking controls via the
  `thinking` parameter:
  - `thinking: { ... }` enables extended thinking.
  - `thinking.budget_tokens` configures how many tokens are allocated to
    internal reasoning (minimum 1,024, must be < `max_tokens`).
  - Only models that advertise `supports_thinking` accept this parameter; using
    it with non-thinking models is an error.
- There is no current mapping from `reasoning_effort` to `thinking` config, and
  no tests asserting Anthropic payload correctness for thinking models.

We also anticipate future “thinking” support in Google’s Gemini models:

- Gemini API exposes `thinkingConfig` for models that support thinking
  (per Google Gen AI docs).
- Some `Part` objects can be marked as `thought=true` to represent model
  reasoning output, and the model resource indicates whether a model supports
  thinking.
- We are not yet running Gemini thinking experiments, but we should design a
  consistent override story now so we can reuse the same `reasoning_effort`
  semantics when we do.

## Plan

- Design provider-agnostic “thinking effort” mapping:
  - Keep `LLMConfigOverridesHTTP.reasoning_effort` as the single cross-service
    hint for “how much thinking/effort”.
  - For each provider that supports thinking (Anthropic now, Gemini later),
    define a clear mapping from `reasoning_effort` to:
    - Anthropic: `thinking` object with `budget_tokens` and enable/disable.
    - Google: `thinkingConfig` (structure to be derived from official SDK/docs).
  - Document the mapping in an internal design note and/or extend ADR‑0020
    (or a new ADR) to cover provider-specific thinking controls.

- Implement Anthropic thinking controls:
  - Extend `AnthropicProviderImpl._make_api_request` to:
    - Accept a normalized “thinking configuration” derived from
      `reasoning_effort` (e.g. map `none` → no `thinking` param; `low`, `medium`,
      `high` → increasing `budget_tokens` fractions of `max_tokens` subject to
      the ≥1,024 constraint).
    - Inject a `thinking` block into the payload only for models that
      `supports_thinking` according to the manifest.
  - Use the model manifest to:
    - Flag which Anthropic models support thinking.
    - Optionally encode default `thinking` budgets per model.
  - Ensure we don’t break existing non-thinking models:
    - If `reasoning_effort` is set for a model that doesn’t support thinking,
      either:
      - log and ignore the hint (documented), or
      - fail fast with a clear configuration error (for ENG5 experiments).

- Plan for Google Gemini thinking controls:
  - From the Gemini API docs, identify:
    - Exact shape of `thinkingConfig`.
    - Constraints and defaults for thinking settings.
  - Define how `reasoning_effort` maps into `thinkingConfig` for models that
    `supports_thinking` in the `Model` resource.
  - Leave Google implementation behind a small feature flag / model-capability
    check so we can activate it when we start running Gemini thinking
    experiments.

- Testing & contracts:
  - Add unit tests for Anthropic provider:
    - For a thinking-enabled model, assert that `reasoning_effort` values map
      to appropriate `thinking.budget_tokens` in the payload.
    - For non-thinking models, assert that adding `reasoning_effort` does not
      produce invalid payloads (either ignored or rejected as per design).
  - Extend cross-provider reasoning tests:
    - Add a simple provider-agnostic test that, given a standard
      `reasoning_effort` override, we can generate a provider-specific call for
      both OpenAI (GPT‑5.x) and Anthropic thinking models without validation
      errors.
  - Once we start implementing Gemini thinking:
    - Add tests for `thinkingConfig` mapping driven by `reasoning_effort`.

## Progress (2025-12-02)

- `AnthropicProviderImpl.generate_comparison` now forwards `reasoning_effort` /
  `output_verbosity` into `_make_api_request`, and `_make_api_request` uses the
  model manifest to detect `extended_thinking` support for each model.
- For Anthropic models with `capabilities["extended_thinking"] = True`
  (for example `claude-haiku-4-5-20251001`), `reasoning_effort` values other
  than `"none"` are mapped to a `thinking` payload with `"type": "enabled"` and
  `budget_tokens` derived as fractions of `max_tokens` and clamped to the
  `[1024, max_tokens)` interval.
- For non-thinking models or models not present in the manifest, reasoning
  hints are ignored and no `thinking` block is added, keeping existing payloads
  unchanged.
- New integration tests in
  `services/llm_provider_service/tests/integration/test_anthropic_prompt_cache_blocks.py`
  assert:
  - `test_reasoning_effort_adds_thinking_block_for_extended_models` – validates
    the presence and shape of the `thinking` block.
  - `test_reasoning_effort_ignored_for_non_thinking_models` – confirms that
    models without `extended_thinking` capability do not receive a `thinking`
    payload even when `reasoning_effort` is provided.

## Success Criteria

- [x] Anthropic provider:
      - Accepts `reasoning_effort` as a knob for thinking-enabled models and
        maps it to a valid `thinking` payload with `budget_tokens` bounded by
        `max_tokens` and the ≥1,024 constraint.
      - Leaves non-thinking models unchanged or fails clearly when thinking is
        misconfigured.
- [x] Shared overrides:
      - `LLMConfigOverridesHTTP.reasoning_effort` remains the single cross-service
        hint for thinking effort across providers; no ad-hoc JSON flags are
        added to metadata.
- [x] Tests:
      - New Anthropic integration tests assert the `thinking` payload structure and
        behaviour for thinking vs non-thinking models.
      - Parametrized tests verify absolute budget values (low=2048, medium=8000, high=16000).
- [ ] Google plan (future):
      - A documented mapping from `reasoning_effort` to Gemini `thinkingConfig`
        is agreed and captured (even if not yet implemented), ready to be used
        when we start running Gemini thinking experiments.

## Related

- `TASKS/infrastructure/llm-provider-openai-gpt-5x-reasoning-controls.md`
- `TASKS/architecture/cj-lps-reasoning-verbosity-metadata-contract.md`
- `docs/decisions/0020-cj-assessment-completion-semantics-v2.md`
- `services/llm_provider_service/implementations/anthropic_provider_impl.py`
- Anthropic API docs (extended thinking / `thinking` parameter)
- Google Gemini API docs (`thinkingConfig`, `supports_thinking`)
