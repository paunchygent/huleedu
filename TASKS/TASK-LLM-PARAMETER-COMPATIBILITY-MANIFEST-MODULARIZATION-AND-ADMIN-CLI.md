# TASK: LLM Parameter Compatibility, Manifest Modularization, and Admin Model Smoke Test CLI

Parent: [TASK-LLM-MODEL-VERSION-MANAGEMENT.md](./TASK-LLM-MODEL-VERSION-MANAGEMENT.md)

## Summary

- Prevent 400s from OpenAI models by introducing model-aware capability validation without changing current defaults (prototyping).
- Keep `model_manifest.py` small and maintainable by modularizing it by provider/family.
- Provide an admin CLI to list, inspect, dry-run, and optionally call models with a minimal payload that mimics CJ Assessment/LLM Provider final requests.

## Goals

- Maintain current runtime defaults and behavior.
- Add a maintainable structure that supports:
  - Per-family capability presets to avoid duplication.
  - Per-model `validate_model_capability` functions (as requested) + a generic validator.
  - Optional dynamic capability overrides (for “updated by API” use-cases) without code changes.
- Provide a CLI that allows real-world confirmation, avoiding assumptions.

## Non-Goals

- No provider call-path behavior change in this task (e.g., no temperature gating, no endpoint switching, no `max_completion_tokens` changes).
- No persistence layer for dynamic overrides (we will stub the integration points only).

## Assumptions

- Defaults remain unchanged during prototyping.
- `model_manifest.py` is the current import surface. We will keep it as a thin re-export after modularization.
- Admin users can execute `pdm run`-based CLIs with the right API keys available via env vars.

## Scope & Deliverables

- Modularization package under `services/llm_provider_service/manifest/` (no behavior change):
  - `types.py`: `ModelConfig`, `ModelRegistry`, `ProviderName`, `StructuredOutputMethod`.
  - `{openai,anthropic,google,openrouter}.py`: family presets, model lists, per-model validators.
  - `__init__.py`: aggregates `SUPPORTED_MODELS` and re-exports helper functions.
  - `model_manifest.py`: converted to thin re-export for back-compat.
- Capability taxonomy (compact):
  - `sampling_policy`: `{ temperature: omit|support|fixed, top_p: omit|support|fixed, freq_penalty: omit|support, presence_penalty: omit|support }`
  - `chat_token_param`: `"max_tokens" | "max_completion_tokens"`
  - `structured_output`: `{ chat_json_schema_supported: bool, preferred_api: "chat" | "responses" }`
  - `reasoning`: `{ is_reasoning_model: bool, default_reasoning_effort?: "minimal"|"medium"|"high" }`
- Per-model validators (generated or simple functions) with a registry:
  - `def validate_model_capability__{normalized_model_id}(capability: str) -> bool`
  - `MODEL_VALIDATORS: dict[str, Callable[[str], bool]]`
  - Generic fallback: `validate_model_capability(provider, model_id, capability)` consults per-model function → model capabilities → (optionally) dynamic overrides.
- Admin CLI (new) to exercise models:
  - List models, show capabilities, dry-run payload (preview), optional real call.
  - Mimic CJ’s final request shape for comparison tasks.

## Why a per-model `def validate_model_capability`?

- Meets the “updated by API” spirit by providing a stable code contract for checks.
- However, functions are static; true runtime updates require a dynamic overrides layer (env/Redis/API). The generic validator will apply overrides last. Therefore: a per-model function alone does not suffice for runtime updates; we add an override mechanism as an extension point.

## Design Details

### 1) Modularization (no behavior change)

- Create `services/llm_provider_service/manifest/` with files listed above.
- Move existing model definitions into provider-specific modules.
- Keep `model_manifest.py` as a thin facade that re-exports the aggregated objects/functions.
- File size and cognitive load drop; future additions occur in provider/family files.

### 2) Capability Taxonomy & Family Presets

- In `openai.py`, define family presets applied to each model family (e.g., GPT-5, GPT-4.1, GPT-4o).
- Individual models only specify deltas (e.g., `vision: True`).
- This keeps each model entry compact and consistent.

### 3) Per-Model Validators & Registry

- For each `model_id`, define a namespaced function that answers capability questions:
  - Example: `validate_model_capability__gpt_4o_mini_2024_07_18("supports_temperature") -> True`
- Map model_id → function in `MODEL_VALIDATORS`.
- Implement `validate_model_capability(provider, model_id, capability)` to:
  1. Use `MODEL_VALIDATORS[model_id]` if present.
  2. Else read `ModelConfig.capabilities.get(capability, False)`.
  3. If `Settings.ENABLE_DYNAMIC_CONFIG` and override exists, apply override (last).

### 4) Dynamic Overrides (optional, no default change)

- Add an adapter interface (stub): `CapabilityOverrides.get(model_id) -> dict[str, Any] | None`.
- Wire this into step (3) above; do not ship a real backend in this task.
- This enables "updated by API" runtime changes without redeploying.

### 5) Admin CLI (Model Smoke Test)

- Location: `services/llm_provider_service/admin_cli.py` (or `scripts/admin/llm_model_smoke_test.py`).
- Commands:
  - `list-models --provider <openai|anthropic|...>`
  - `show-capabilities --provider <p> --model <id>`: shows manifest + per-model validator results.
  - `dry-run-payload --provider <p> --model <id> [--temperature <f>] [--max-tokens <n>] [--responses-api]`:
    - Prints the payload the provider would send per manifest rules (no network call).
    - For now, mimic current provider behavior (since we won’t change it), but also print a “recommended payload adjustments” section based on capability checks (e.g., “omit temperature”, use `max_completion_tokens`, switch to Responses API for JSON schema). This helps admins verify what will be implemented next.
  - `call --provider <p> --model <id> [--essay-a <text|path>] [--essay-b <text|path>] [--system <text>] [--timeout <s>]`:
    - Executes a real call via the existing provider code path (`generate_comparison`), using minimal content by default (e.g., `"A"` / `"B"`) and current defaults (may 400 for unsupported params, which is acceptable in prototyping to reveal incompatibilities).
    - Outputs response summary or error code + message. Supports `--json` output.
- Minimal CJ-like payload (matches current OpenAI provider schema):
  - Winner enum: `"Essay A" | "Essay B"`
  - `justification` (<=50 chars)
  - `confidence` (1.0–5.0)
- Example usage:
  - `pdm run python -m services.llm_provider_service.admin_cli list-models --provider openai`
  - `pdm run python -m services.llm_provider_service.admin_cli show-capabilities --provider openai --model gpt-4o-mini-2024-07-18`
  - `pdm run python -m services.llm_provider_service.admin_cli dry-run-payload --provider openai --model gpt-5-mini-2025-08-07 --max-tokens 512`
  - `pdm run python -m services.llm_provider_service.admin_cli call --provider openai --model gpt-4o-mini-2024-07-18 --essay-a 'A' --essay-b 'B'`
- Notes:
  - Environment: requires appropriate API keys (e.g., `OPENAI_API_KEY`).
  - The `dry-run` will surface the recommended adjustments before we implement provider-side gating.

## Risks & Mitigations

- Duplication across per-model functions: mitigated by family presets and generated helper to create validators.
- Divergence between capabilities dict and validators: mitigated by unit tests and the generic validator precedence.
- Runtime updates vs static validators: addressed via optional dynamic overrides (feature-gated).

## Testing Plan

- Unit tests:
  - Aggregation and back-compat (`model_manifest.py` still re-exports helpers; defaults unchanged).
  - A few per-model validator functions return expected values for canonical capabilities.
  - Generic fallback behavior.
  - CLI `dry-run` prints capability summary and recommended adjustments.
- (Future when provider changes are implemented): tests for payload selection (temperature omission, token parameter switch, response_format gating).

## Acceptance Criteria

- `model_manifest.py` remains import-compatible; no runtime defaults changed.
- New `manifest/` package exists and aggregates to the same `SUPPORTED_MODELS` and helper functions.
- Per-model validators present + registry, with generic validator precedence.
- Admin CLI supports `list-models`, `show-capabilities`, `dry-run-payload`, `call`.
- Unit tests for validators and CLI `dry-run` output are added and passing.

## Rollout

- Phase 1 (this task): Modularization + validators + CLI (dry-run + call). No provider changes.
- Phase 2 (separate task): Provider conditional parameter sending, endpoint selection, and token param switching; update CLI `dry-run` to match new behavior.

## Timeline

- Phase 1: 0.5–1.5 days (implementation + tests + docs).
- Phase 2: 1–2 days (provider changes + tests).

## Ownership

- Primary: LLM Provider module owners
- Review: Architect Lead (this task is aligned with Context7 and project rules)

## References

- Parent Task: [TASK-LLM-MODEL-VERSION-MANAGEMENT.md](./TASK-LLM-MODEL-VERSION-MANAGEMENT.md)
- Current manifest and provider code:
  - `services/llm_provider_service/model_manifest.py`
  - `services/llm_provider_service/implementations/openai_provider_impl.py`
  - `services/llm_provider_service/config.py`
- Doc context: Reasoning model constraints and structured outputs (OpenAI/Azure docs)
