---
id: 'research-plan-richer-mock-llm-provider'
title: 'Research plan: richer mock LLM provider'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'architecture'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-26'
last_updated: '2025-11-26'
related: []
labels: []
---
# Research plan: richer mock LLM provider

## Objective

Design and specify an improved mock LLM provider that better mirrors production behavior while remaining deterministic, fast, and safe to run in integration tests and local dev.

## Context

- Current mock returns deterministic outputs but lacks realism (no latency, no failure modes, simplistic token usage).
- Integration/E2E tests would benefit from exercising retries, cost/metrics, prompt-cache paths, and CJ/LPS contracts without hitting real providers.
- We now expose `ALLOW_MOCK_PROVIDER`/`MOCK_PROVIDER_SEED`; this research should propose the next set of capabilities and guardrails.

## Plan

1) **Survey best practices & libraries**
   - Review existing OSS LLM simulators/mocks (e.g., local OpenAI-compatible stubs, LiteLLM mock, VCR/Betamax patterns for HTTP replay) for reusable components.
   - Identify drop-in helpers for latency/failure injection (e.g., `asyncio.sleep` with jitter, `tenacity`-style patterns) and token estimation (tiktoken/OpenAI tokenizer equivalents).

2) **Define feature set & toggles** (prioritized)
   - Latency + jitter envelopes (per-provider defaults, env-tunable).
   - Error injection matrix (rate, code mix 429/503/500, optional bursty patterns).
   - Token accounting approximation from prompt length/model family; emit usage + cost estimates.
   - Prompt-cache semantics: deterministic cache hits on identical prompt hash; emit `cache_read_input_tokens` / `cache_creation_input_tokens` accordingly.
   - Outcome realism: winner/justification/confidence derived from seeded heuristics (hash/keyword scoring) instead of fixed strings.
   - Optional “streaming metadata” flag to exercise client handling without actual chunking.

3) **Design configuration surface**
   - Propose env var schema (sane defaults, per-feature enable/disable, seed control) and document interactions with `LLM_PROVIDER_SERVICE_USE_MOCK_LLM` and `LLM_PROVIDER_SERVICE_ALLOW_MOCK_PROVIDER`.
   - Ensure deterministic mode for tests and stochastic mode for manual testing.

4) **Implementation outline**
   - Choose implementation home (MockProviderImpl) and structure (pure functions vs strategy objects) to keep code small/testable.
   - Reuse existing tracing/metrics hooks so added behaviors surface in Prometheus and callbacks.
   - Ensure compatibility with queue processor batching and existing API contracts.

5) **Validation plan**
   - Define unit/integration test matrix covering: latency bounds, error rates, cache-hit determinism, token usage monotonicity, and metadata preservation.
   - Identify any CI flags to keep default paths fast (e.g., disable latency/error by default in CI).

## Success Criteria

- Written proposal summarizing chosen libraries/patterns, configuration schema, and implementation plan (<=2 pages).
- Agreed feature set with defaults that keep CI fast and deterministic.
- Test plan covering new behaviors without slowing the suite materially.

## Related

- services/llm_provider_service/implementations/mock_provider_impl.py
- tests/integration/test_cj_lps_metadata_roundtrip.py
- .claude/rules/020.13-llm-provider-service-architecture.md

---

## Proposal (draft ≤2 pages)

### 1 Target behaviours (prioritized)
- **Latency + jitter**: simulate provider RTT with env-tunable base + jitter per provider. Defaults: 0 ms base / 0 ms jitter in CI; 80±40 ms local dev to expose retry/backoff code.
- **Error injection**: probabilistic failures (independent Bernoulli) with configurable mix of 429/503/500. Defaults off in CI; suggest 1–2% in local dev. Burst mode (optional) to create short spikes.
- **Token accounting + cost**: estimate prompt/completion tokens from input length using lightweight tokenizer (tiktoken for OpenAI-compatible; fallback simple word->token ratio). Emit `usage`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `cost_estimate` aligned with existing metrics/events.
- **Prompt-cache semantics**: deterministic cache hits on identical prompt hash; emit `cache_read_input_tokens` and `cache_creation_input_tokens` mirroring real Anthropic/OpenAI cache fields. Default: 50% hit rate on repeated hashes; controllable via env.
- **Outcome realism**: winner/justification/confidence derived from seeded heuristics (e.g., hash parity + keyword scoring) to avoid identical outputs while staying deterministic. Confidence scaled to 1–5 with mild variance.
- **Streaming metadata flag**: non-streaming payload with `streaming_simulated=true` to exercise client logic without chunked transport.
- **Per-provider personalities**: optional small variations (temperature bias, justification length) keyed by provider enum to catch provider-specific branches.

### 2 Configuration surface (env, prefix `LLM_PROVIDER_SERVICE_`)
- `MOCK_LATENCY_MS=0` (base), `MOCK_LATENCY_JITTER_MS=0`
- `MOCK_ERROR_RATE=0.0` (0–1 float); `MOCK_ERROR_CODES=429,503,500`; `MOCK_ERROR_BURST_RATE=0.0`; `MOCK_ERROR_BURST_LENGTH=0`
- `MOCK_CACHE_HIT_RATE=0.0` (0–1); `MOCK_CACHE_ENABLED=true`
- `MOCK_TOKENIZER=tiktoken|simple`; `MOCK_TOKENS_PER_WORD=0.75` (fallback multiplier)
- `MOCK_OUTCOME_MODE=heuristic|fixed`; `MOCK_CONFIDENCE_BASE=4.5`; `MOCK_CONFIDENCE_JITTER=0.3`
- `MOCK_STREAMING_METADATA=false`
- Existing: `LLM_PROVIDER_SERVICE_ALLOW_MOCK_PROVIDER`, `LLM_PROVIDER_SERVICE_USE_MOCK_LLM`, `LLM_PROVIDER_SERVICE_MOCK_PROVIDER_SEED`

Defaults: all noisy behaviours off in CI (latency/error/cache-hit=0), modest realism in dev via `.env.local` example.

### 3 Library choices & reuse
- **Latency/error**: native `asyncio.sleep`; no new deps. For burst patterns, simple ring buffer counters.
- **Token estimation**: prefer `tiktoken` (already transient in many stacks); fallback lightweight estimator to avoid hard dependency when not available.
- **Randomness**: `random.Random(seed)` kept inside MockProviderImpl to ensure determinism per request and reproducibility.
- **Config**: extend existing Pydantic Settings; keep defaults zero-cost for CI.
- **Metrics/logs**: reuse current metrics counters; add labels for `mock_reason`, `cache_hit` booleans; keep Prometheus cardinality bounded (no free-form strings).

### 4 Implementation outline
1. Extend settings with new mock-related fields (booleans/rates/latencies).
2. In MockProviderImpl:
   - Derive per-request RNG from `MOCK_PROVIDER_SEED` + correlation_id hash for determinism.
   - Apply latency sleep if configured.
   - Roll failure before generation; choose status/code from configured distribution.
   - Compute token usage; set `usage` + cost_estimate; derive cache hits based on prompt hash and hit rate; populate cache_* metadata.
   - Generate outcome via heuristic (e.g., SHA256(prompt) parity -> winner; justification template; confidence with jitter clamp 1–5).
   - Attach metadata fields (`resolved_provider`, `queue_processing_mode`, existing prompt_sha256, cache fields, streaming flag).
3. Keep code path behind MockProviderImpl only; DI already registers mock alongside real providers when allowed.

### 5 Validation & tests
- Unit tests for: latency bounds, error-rate stats (binomial tolerance), cache-hit determinism per hash, token estimation monotonicity, confidence bounds, reproducibility with fixed seed.
- Integration regression: existing CJ↔LPS metadata roundtrip should still pass; add one new integration that enables error/latency to ensure retries/metrics don’t break contracts.
- Performance guard: assert mock path adds <5 ms overhead when features disabled.

### 6 Risks / mitigations
- **Flaky tests** from randomness: default all rates to 0 in CI; use seeded RNG per test.
- **Dependency bloat**: keep tiktoken optional with graceful fallback.
- **Cardinality**: constrain labels/metadata to fixed enums/booleans.

### 7 Effort / sequencing (est.)
- Settings + wiring: 1–2h
- MockProviderImpl enhancements: 4–6h
- Tests (unit + one integration): 3–4h
- Docs/README update + examples: 1h
