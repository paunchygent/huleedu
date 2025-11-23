---
id: cj-prompt-cache-benchmark
title: CJ Prompt Cache Benchmark & Warm-Up Validation
type: task
status: paused
priority: medium
domain: assessment
owner_team: agents
created: '2025-11-22'
last_updated: '2025-11-23'
service: cj_assessment_service, llm_provider_service
owner: ''
program: ''
related: [cj-prompt-cache-template-builder, lps-rate-limiting-implementation]
labels: [cache-optimization, benchmarking, anthropic-api]
---

# Task: CJ Prompt Cache Benchmark & Warm-Up Validation (Paused)

## Goal
Design and execute a reproducible benchmark to validate Anthropic prompt caching efficacy (hit rate, token savings, latency) and warm-up scheduling behavior without breaching tier-1 rate limits.

## Scope
- CJ + LPS integration with prompt_blocks.
- Anthropic provider (tier-1 limits).
- Assignment-scope workloads (representative batch fixtures).

## Acceptance Criteria
- Seed exactly one request per unique prompt hash (static cacheable blocks + tool schema); essays remain non-cacheable.
- Post-seed miss rate per hash ≤20% and converges to near-0 on the next request (5m window).
- Assignment-scope hit rate >80% after warmup.
- TTL ordering upheld (1h before 5m) respecting `USE_EXTENDED_TTL_FOR_SERVICE_CONSTANTS`; zero TTL violations.
- Warm-up scheduling avoids concurrent first-writes (ordered or jittered).
- Callback metadata includes `prompt_sha256` and cache usage fields without overwriting caller metadata.
- Zero rate-limit hits (429/Retry-After) during benchmark runs; obey request/token budgets (≈50 req/min, ≈40k input tok/min cap).

## Deliverables
- Benchmark runner (CLI) with seed+jitter and dual token/request buckets (temporary throttling until service-level rate limiting from `lps-rate-limiting-implementation` lands).
- Structured results: `.claude/work/reports/benchmarks/<timestamp>-prompt-cache-warmup.json` plus brief summary `.md`.
- PromQL snapshots embedded in results (hit/miss, tokens saved, TTL violations, scope mix).
- Optional Grafana snapshot links/PNGs (dashboard uid `huleedu-llm-prompt-cache`).

## Open Questions
- Seed jitter/ordering: exact algorithm and defaults.
- Fixture selection: which batch size/composition to use; synthetic vs recorded.
- CI gating: thresholds for warn vs fail on hit rate/miss rate/latency.
- Artefact retention policy and naming.

## Decisions (2025-11-22)
- Warm-up scheduling: Option A chosen — fully serialized seeds (concurrency=1) with 50–150 ms jitter; prioritize correctness and zero first-write collisions.
- Main-run pacing: dual buckets in runner at 50 req/min and 25–30k input tok/min (below tier-1) with per-request debits; retain until service limiter ships.
- Fixtures: use two tiers — smoke (4 essays × 4 anchors, ~24 comps) for preflight; full benchmark (10 essays × 10 anchors, ~100 comps) with real rubric/system blocks once smoke is green.
- CI thresholds: hit rate warn <85%, fail <80; post-seed miss per hash warn >20%, fail >30; TTL violations fail on any; 429/Retry-After fail on any; latency regression p95 warn >15–20%, fail deferred until prod rollout (not enforced in prototype runs).
- Smoke test protocol (2025-11-23): A (synthetic 4×4) then B (ENG5 real 4×4); validate tooling before production-like data. Created `data/eng5_smoke_fixture.json` (4 anchors/students from full 12×12) for deterministic B run without loader filtering logic.
- Redaction control (2025-11-23): Default `--redact-output` (hash/metrics only); `--no-redact-output` for validation (adds essay text, prompts, blocks to JSON artefacts).

## Plan
1) Implement benchmark runner with chosen jitter/concurrency and dual buckets; configurable limits via CLI flags.
2) Run smoke fixture; if green, lock exact full-fixture parameters and execute full benchmark.
3) Persist artefacts (JSON + MD) with config, per-hash hit/miss, tokens saved, TTL violations, 429 counts, PromQL snapshots, Grafana links.
4) Revisit latency fail threshold when production rollout approaches (target within 6 months).

## Progress (2025-11-22)
- Added Typer CLI `pdm run prompt-cache-benchmark` with serialized seeding (50–150ms jitter), dual request/token buckets, optional extended TTL, PromQL snapshots, and artefact writers.
- Built fixtures (`scripts/prompt_cache_benchmark/fixtures.py`) for smoke (4×4) and full (10×10) anchor/student cross-products using PromptTemplateBuilder so cacheable blocks carry content hashes.
- Added wrapper scripts `scripts/run-prompt-cache-smoke.sh` and `scripts/run-prompt-cache-full.sh`, plus report templates under `.claude/work/reports/benchmarks/`.
- Unit coverage: rate limiter budgeting and runner aggregation (`scripts/tests/test_prompt_cache_benchmark.py`); format/lint/typecheck/pytest all green.
- ENG5 real-data path: new exporter `python -m scripts.prompt_cache_benchmark.build_eng5_fixture` generates `data/eng5_prompt_cache_fixture.json` from existing ENG5 DOCX assets (12 anchors + 12 students + prompts/rubric/system prompt). CLI now accepts `--fixture-path` to use this JSON instead of synthetic fixtures. Default: `--redact-output` (hash/metrics only); use `--no-redact-output` for validation runs (adds essay text, prompts, blocks to JSON).
- Created `data/eng5_smoke_fixture.json` (4×4 subset from full) for A/B smoke test parity; both synthetic and ENG5 smoke now execute 16 comparisons with identical operational profile.
- Pre-flight smoke A executed (2025-11-23): **100% failure (16/16) — HTTP 400 "metadata.correlation_id: Extra inputs are not permitted"**. Anthropic API `metadata` field only accepts `user_id`; custom fields (`correlation_id`, `provider`, `prompt_sha256`) rejected. Location: `anthropic_provider_impl.py:556-572`. Open question: Remove fields from API payload (confirm response metadata + callback propagation unaffected); verify no regression in queue_processor (line 1084: reads `prompt_sha256` from response.metadata) or downstream consumers.

## Current Status (2025-11-23)

- Synthetic + ENG5 fixtures wired; CLI (`pdm run prompt-cache-benchmark`) with dual-bucket limiter and jittered seeds. Artefacts live in `.claude/work/reports/benchmarks/`.
- Haiku caching: bypass (cacheable prefix ~1.0-1.3k tokens < 2,048 floor). Sonnet caching works without inflating prompts (1,024 floor).
- Runs to date:
  - Smoke A redacted (Haiku): 15/16 success, 1 validation_error (justification >500), cache bypass.
  - Smoke A unredacted (Haiku): 16/16 success, cache bypass; artefacts `.claude/work/reports/benchmarks/20251123T004138Z-prompt-cache-warmup.{json,md}`.
  - Smoke B (ENG5 smoke) Sonnet: cache reads 23,925 / writes 20,595; hits double-counted in stored artefact (effective hits 15/16). Artefacts `.claude/work/reports/benchmarks/20251123T005924Z-prompt-cache-warmup.{json,md}` + normalized post-process `.json`.
- Smoke B (ENG5 smoke) Sonnet with raw_response capture: hits 16, misses 0, bypass 0; read 43,112 / write 1,408; artefacts `.claude/work/reports/benchmarks/20251123T011800Z-prompt-cache-warmup.{json,md}` (includes raw Anthropic tool responses).
- Validator cap raised to 1000 chars; tool schema still enforces 50-char justification; prompt text explicitly asks for ≤50 chars. Anthropic beta header added; payload metadata restricted to `user_id`.
- CLI help now warns: do not wrap the command in external timeouts; prior 180s wrapper killed runs after requests were sent.
- LLM Provider queue processor completion/removal integration tests now pass despite `.env` defaulting `QUEUE_PROCESSING_MODE=serial_bundle`; `_process_request` always uses the per-request path. Verified via `pdm run pytest-root services/llm_provider_service/tests/integration/test_queue_processor_completion_removal.py`.
- Paused: further validation runs are deferred until the go-live window; current smoke artefacts are sufficient for operational decisions.

## Risks / Blockers

- Haiku prompt caching floor (2,048 tokens) exceeds current cacheable prefix; would require inflating static blocks to see writes/reads.
- Tier-1 Anthropic limits still apply; full-run concurrency must stay within bucket budgets.

## Next Steps (Deferred)

- Final full-scale validation runs are on hold until the deployment window; keep Sonnet as the caching baseline.
- Optional: rerun Smoke B on Haiku with inflated cacheable prefix to validate cache writes (cost/latency tradeoff).
- Optional: post-process existing artefacts to slim raw_response for BT-score input (no new API calls).
