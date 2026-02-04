---
id: 'hemma-offload-combined-extract-endpoint'
title: 'Hemma offload: single extract endpoint (embeddings + spaCy + LanguageTool)'
type: 'task'
status: 'proposed'
priority: 'high'
domain: 'assessment'
service: 'nlp_service'
owner_team: 'agents'
owner: ''
program: 'huledu_alpha_launch'
created: '2026-02-03'
last_updated: '2026-02-03'
related: []
labels: []
---
# Hemma offload: single extract endpoint (embeddings + spaCy + LanguageTool)

## Executive Summary

- **Purpose**: Make the essay-scoring research pipeline run with **zero heavy NLP runtime** on the dev machine by offloading **all feature extraction** (embeddings + spaCy/TextDescriptives + LanguageTool-derived error densities) to Hemma.
- **Scope**: Add a **single combined offload endpoint** that returns the complete feature payload needed for `FeatureSet=embeddings|handcrafted|combined`, plus version metadata for reproducibility and cache correctness.
- **Integration context**: This is a research-scoped service under `scripts/` (not `services/`) and is operated on Hemma via `docker-compose.hemma.research.yml` behind a single SSH tunnel (`localhost:19000 -> hemma:9000`).

## Non-goals

- Multi-language support (English-only for now).
- Public exposure of offload endpoints (Hemma localhost-only + tunnels only).
- Backward-compatible “legacy” CLI paths for mixed local/remote feature extraction when `backend=hemma` (explicit fail-fast instead).

## Critical Constraints (non-negotiable)

- **Zero local fallbacks** when `backend=hemma`: the Mac must not parse with spaCy, must not call LanguageTool directly, and must not run local torch/transformers embedding.
- **Single tunnel** for Hemma offload in `backend=hemma` mode: only `:19000` is required from the dev machine.
- **Pinned English spaCy model**: `en_core_web_sm` (exact wheel version pinned and recorded in response metadata).
- **Single combined endpoint** is the canonical client integration point (no “compute embeddings twice” design).
- **Strict contract + versioning**: response must include `schema_version` + `server_fingerprint` so caches are safe and reproducible.

## Context

The current research pipeline still parses spaCy locally (Tier1/Tier2/Tier3) while optionally
offloading:
- embeddings (Hemma `/v1/embed`)
- LanguageTool checks (Hemma `language_tool_service`)

This creates three problems for long-term stability and ergonomics:
- **Operational complexity**: requires multiple tunnels and mixed local/remote plumbing.
- **Duplication**: embeddings used for Tier2 similarity features are computed separately from the main embedding matrix.
- **Drift risk**: when parts run locally and parts run remotely, version skew is easy and hard to diagnose.

This task makes Hemma the single “feature factory” for the research build.

## Proposed Contract (v1)

### Endpoint

- `POST /v1/extract`
- Request: `application/json`
- Response: `application/zip` (binary)

### Request body (shape)

- `texts: list[str]` (essay texts; required; length N)
- `prompts: list[str]` (prompt per essay; required; length N)
- `feature_set: "handcrafted" | "embeddings" | "combined"` (required; aligns with research pipeline)
- Optional, but must be validated strictly:
  - embedding config overrides (max_length, batch_size) **only if** we explicitly decide to support them; otherwise forbid.

### Response bundle (zip)

Zip contains:
- `meta.json`
  - `schema_version` (int)
  - `server_fingerprint` (string; hash of server config + key dependency versions + model IDs)
  - `git_sha` (server repo SHA for traceability)
  - `versions` (spacy/textdescriptives/transformers/torch/etc.)
  - `feature_schema` (tier1/tier2/tier3 feature name ordering; must match training schema)
  - `embedding` (model_name, embedding_dim, max_length, pooling)
  - `language_tool` (language, request options)
- `embeddings.npy` (float32 matrix `[N, D]`) when `feature_set in {"embeddings","combined"}`
- `handcrafted.npy` (float32 matrix `[N, H]`) when `feature_set in {"handcrafted","combined"}`

Error handling:
- Non-2xx responses are JSON with `{error, detail, correlation_id}`.
- If internal LanguageTool dependency is unavailable: return `503` and fail-fast (no fallback).

## Architecture (SRP-aligned)

Even though the client consumes a single endpoint, the server implementation must stay modular:
- **Contract models**: request/response meta models (Pydantic; `extra="forbid"`).
- **Extract orchestrator**: owns per-request orchestration + batching + dependency calls.
- **Embedding provider**: wraps `DebertaEmbedder`.
- **spaCy runtime**: loads `en_core_web_sm` once; exposes two pipelines:
  - `nlp_fast` (parser/tagger/senter; no readability)
  - `nlp_readability` (adds TextDescriptives readability)
- **LanguageTool client**: HTTP client to `language_tool_service` (compose network), bounded concurrency, deterministic derived counts.
- **Bundle writer**: builds `meta.json` + `.npy` arrays into a zip payload.
- **Metrics**: extend offload metrics collection to cover combined endpoint timings and dependency errors.

## Execution Checklist (update after each phase)

**Rule**: every time a phase is completed, update this section:
- tick the checklist items
- add evidence (commands, output dirs, Hemma health checks, and commit SHAs)
- if a decision is made (limits, schema changes), record it under the phase evidence

### Phase 0 — Architecture study + baseline

- [ ] Confirm canonical feature ordering source: `scripts/ml_training/essay_scoring/features/schema.py`
- [ ] Record baseline timings (local-only vs current mixed offload) on a fixed small dataset
- [ ] Append the benchmark results to `docs/operations/ml-nlp-runbook.md` (experiment log)
- Evidence:
  - Commands:
  - Run dirs:
  - Notes/decisions:

### Phase 1 — Contract + versioning + payload format

- [x] Define Pydantic request/response models for `/v1/extract` (`extra="forbid"`)
- [x] Define and test `server_fingerprint` inputs and output format
- [x] Decide and document request limits (N, request bytes, response size)
- [x] Document zip contents (`meta.json`, `embeddings.npy`, `handcrafted.npy`) and error response format
- Evidence:
  - Code refs:
    - `scripts/ml_training/essay_scoring/offload/extract_models.py`
    - `scripts/ml_training/essay_scoring/offload/settings.py`
    - `scripts/ml_training/essay_scoring/offload/server.py`
  - Notes/decisions:
    - Limits: `N<=64`, `request_bytes<=900_000`, `response_bytes<=8_000_000` (enforced server-side).
    - Contract: `POST /v1/extract` returns `application/zip` with `meta.json` + optional `embeddings.npy` / `handcrafted.npy`; non-2xx returns JSON `ExtractError`.
    - Fingerprint: sha256 of canonical JSON including schema_version, embedding config + dim, feature schema, runtime versions, and `OFFLOAD_LANGUAGE_TOOL_JAR_VERSION` (required).

### Phase 2 — Hemma offload server: implement `/v1/extract`

- [x] Implement `/v1/extract` endpoint in `scripts/ml_training/essay_scoring/offload/server.py`
- [x] Implement internal LanguageTool client calls (no Mac tunnel), bounded concurrency
- [x] Add readiness gating: fail if LanguageTool dependency unavailable (503; no fallback)
- [x] Ensure embeddings used for Tier2 similarity + embeddings matrix are computed once per request
- Evidence:
  - Code refs:
    - `scripts/ml_training/essay_scoring/offload/server.py`
    - `scripts/ml_training/essay_scoring/offload/settings.py`
  - Notes/decisions:
    - `/healthz` reports config issues (e.g. missing `OFFLOAD_LANGUAGE_TOOL_JAR_VERSION`) as `status=degraded`.
    - Request-scoped embedding cache ensures Tier2 embedding calls are reused for `embeddings.npy` (no duplicate embedding compute).

### Phase 3 — Hemma runtime + compose wiring

- [x] Add spaCy + TextDescriptives + pinned `en_core_web_sm` to the offload runtime dependency set
- [x] Update offload Dockerfile to install the above without pulling training deps
- [x] Update `docker-compose.hemma.research.yml`:
  - [x] set `OFFLOAD_LANGUAGE_TOOL_URL=http://language_tool_service:8085`
  - [x] ensure service dependency order / health gating
- Evidence:
  - Code refs:
    - `pyproject.toml`
    - `scripts/ml_training/essay_scoring/offload/Dockerfile`
    - `docker-compose.hemma.research.yml`
  - Notes/decisions:
    - Compose requires `OFFLOAD_LANGUAGE_TOOL_JAR_VERSION` via `${...:?Missing ...}` (fail-fast deploy).

### Phase 4 — Research pipeline client: Hemma backend (zero fallbacks)

- [x] Add `backend: local|hemma` and `offload_service_url` to research config/CLI
- [x] Implement `RemoteExtractClient` (download+unzip+load+validate)
- [x] Implement Mac-side disk caching keyed by `server_fingerprint` + schema + text/prompt hashes
- [x] Update `FeaturePipeline` to enforce: when `backend=hemma`, do not import/use local spaCy/LanguageTool/torch embeddings
- Evidence:
  - Code refs:
    - `scripts/ml_training/essay_scoring/config.py`
    - `scripts/ml_training/essay_scoring/cli.py`
    - `scripts/ml_training/essay_scoring/offload/extract_client.py`
    - `scripts/ml_training/essay_scoring/features/pipeline.py`
  - Notes/decisions:
    - Hemma mode forbids `embedding_service_url`/`language_tool_service_url` and requires `offload_service_url` (single-tunnel).
    - Extract meta is persisted to `artifacts/offload_extract_meta.json` for reproducibility.

### Phase 5 — Tests + determinism guarantees

- [x] In-process HTTP test for `/v1/extract` validates zip structure + meta + array shapes
- [x] “No fallback” test: `backend=hemma` fails fast when offload URL missing/unreachable
- [ ] Parity test on a tiny sample for handcrafted features (document acceptable tolerances)
- Evidence:
  - Test commands:
    - `source .env && pdm run pytest-root scripts/ml_training/tests -q`
  - Notes/decisions:
    - Added tests cover zip/meta/shape + client caching + fail-fast Hemma config.

### Phase 6 — Runbooks + Hemma verification

- [x] Update runbooks to make `:19000` the only required tunnel for Hemma backend runs
- [x] Redeploy on Hemma and verify:
  - [x] `/healthz` and readiness reflect dependency health
  - [x] `/v1/extract` works for `feature_set=combined`
  - [x] warm-cache run on Mac does not call Hemma for cached items
- [x] Record performance metrics and tuning notes using `offload_metrics.json`
- Evidence:
  - Docs refs:
    - `docs/operations/hemma-server-operations-huleedu.md`
    - `.claude/work/session/readme-first.md`
  - Notes/decisions:
    - Hemma `.env` requires `OFFLOAD_LANGUAGE_TOOL_JAR_VERSION` (cache safety; LT service does not expose jar version in its current API).
  - Evidence:
    - Hemma git:
      - `git pull --ff-only` to `d9d26dae` (2026-02-04)
    - Hemma env:
      - `OFFLOAD_LANGUAGE_TOOL_JAR_VERSION=6.6`
    - Hemma deploy:
      - `sudo docker compose -f docker-compose.hemma.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml --profile research-offload up -d --build essay_embed_offload`
    - Hemma health checks:
      - `curl -fsS http://127.0.0.1:9000/healthz` → includes `extract.max_items=64`, `extract.max_request_bytes=900000`, `extract.max_response_bytes=8000000`, `extract.language_tool_url=http://language_tool_service:8085`, `extract.language_tool_jar_version=6.6`
      - `curl -fsS http://127.0.0.1:9000/v1/extract ...` smoke succeeded (zip bundle with `meta.json` + `embeddings.npy` + `handcrafted.npy`)
    - Mac tunnel:
      - single tunnel confirmed active: `ssh hemma -L 19000:127.0.0.1:9000 -N`
    - Mac live CLI (Hemma backend):
      - `source .env && pdm run essay-scoring-research run --dataset-kind ellipse --feature-set combined --ellipse-train-path /tmp/ellipse_train_smoke.csv --ellipse-test-path /tmp/ellipse_test_smoke.csv --backend hemma --offload-service-url http://127.0.0.1:19000 --skip-shap --skip-grade-scale-report --run-name hemma_extract_smoke`
      - Output: `output/essay_scoring/20260204_005102_hemma_extract_smoke`
      - Meta: `artifacts/offload_extract_meta.json` includes `schema_version=1`, `server_fingerprint=...`, `language_tool.jar_version=6.6`
    - Warm-cache verification:
      - Re-run with same inputs produced: `output/essay_scoring/20260204_005206_hemma_extract_smoke_cached`
      - Offload server `/metrics` counters did **not** increase for `/v1/extract` across the second run (cache hit).
    - Metrics artifacts:
      - `output/essay_scoring/20260204_005102_hemma_extract_smoke/artifacts/offload_metrics.json`

## Implementation Phases (full plan)

### Phase 0 — Architecture study + baseline
- Identify current “handcrafted” feature ordering contract (`scripts/ml_training/essay_scoring/features/schema.py`) and ensure it is treated as the canonical ordering.
- Measure baseline wall time on a small fixed dataset for:
  - `FeatureSet=combined` local-only
  - current mixed offload (embedding + LanguageTool only)

### Phase 1 — Define contract + versioning + payload format
- Add request/response models under `scripts/ml_training/essay_scoring/offload/` for `/v1/extract`.
- Define `server_fingerprint` algorithm (inputs: schema_version, spacy model + version, textdescriptives version, embedding model name, max_length, pooling, language tool config).
- Decide and document request limits:
  - max N per request
  - max request bytes
  - expected response size ceiling

### Phase 2 — Hemma offload server: implement `/v1/extract`
- Extend `scripts/ml_training/essay_scoring/offload/server.py` with `/v1/extract`.
- Add Hemma-only dependency wiring:
  - `OFFLOAD_LANGUAGE_TOOL_URL` defaults to `http://language_tool_service:8085`
  - health/readiness checks include LanguageTool dependency reachability.
- Implement “all-in-one” extraction flow for one request:
  - Compute Tier1 stats + readability via `nlp_readability`
  - Compute Tier2 deterministic syntactic features via `nlp_fast`
  - Compute Tier2 embedding-derived similarity features using a single embedding model invocation (no second endpoint call)
  - Compute Tier3 structure/lexical/POS features via `nlp_fast`
  - Fetch LanguageTool results internally and derive grammar/spelling/punctuation counts → densities

### Phase 3 — Docker/runtime dependencies for Hemma (research-offload image)
- Add `spacy`, `textdescriptives`, and pinned `en_core_web_sm` to the offload runtime dependency set (and ensure the Dockerfile installs them).
- Ensure `docker-compose.hemma.research.yml` sets:
  - `OFFLOAD_LANGUAGE_TOOL_URL=http://language_tool_service:8085`
  - `depends_on: language_tool_service` for `essay_embed_offload` (and optionally health-gated start).
- Confirm the HuggingFace cache mount and `HF_TOKEN` flow remain intact.

### Phase 4 — Research pipeline client: “hemma backend” with zero fallbacks
- Add a single `offload_service_url` to `OffloadConfig` and add `backend: local|hemma`.
- Implement a `RemoteExtractClient` that:
  - calls `/v1/extract`
  - unzips, loads `.npy` arrays, validates shapes, validates `server_fingerprint`
  - writes Mac-side caches (per essay/prompt) for embeddings + handcrafted features.
- Update `FeaturePipeline` so that when `backend=hemma`:
  - it does not initialize `load_spacy_model(...)` locally
  - it does not run local LanguageTool calls
  - it does not use local DeBERTa embeddings
  - it only calls the offload service (and merges cached results)

### Phase 5 — Tests + determinism guarantees
- Add an in-process HTTP test for `/v1/extract`:
  - validates zip structure, meta schema, and array shapes.
- Add a “no fallback” test: `backend=hemma` must raise a clear error if `offload_service_url` missing/unreachable.
- Add a feature parity test for a tiny sample that compares:
  - local handcrafted features vs Hemma handcrafted features (within tolerances), while acknowledging that LanguageTool responses may vary with version.

### Phase 6 — Ops/runbooks + verification on Hemma
- Update runbooks to make `:19000` the only required tunnel for Hemma backend runs.
- Redeploy on Hemma and verify:
  - `/healthz` and readiness reflect dependency health
  - `/v1/extract` works for `feature_set=combined`
  - warm-cache run on Mac does not call Hemma for previously cached items
  - `offload_metrics.json` is emitted and useful for tuning

## Success Criteria

- `pdm run essay-scoring-research ... --backend hemma --offload-service-url http://127.0.0.1:19000` runs end-to-end without requiring `--language-tool-service-url` or `--embedding-service-url`.
- Feature extraction produces:
  - embeddings matrix `[N, 768]` (or configured dimension) and handcrafted matrix `[N, H]` with stable ordering.
- When Hemma dependencies are down (LanguageTool/offload), the pipeline fails fast with actionable error messages (no local fallback).
- Response metadata contains `schema_version`, `server_fingerprint`, and `git_sha` and is persisted with run artifacts for reproducibility.

## Risks & Mitigations

- **Version skew** (spaCy/TextDescriptives changes change features): pin versions + include `server_fingerprint` in cache keys and run metadata.
- **Large payloads** (zip too big): enforce per-request limits + implement batching in client.
- **LanguageTool throughput**: bounded concurrency + reuse the existing Mac-side “warm-cache” strategy, but at the extract-result layer.
- **HF rate limits**: require `HF_TOKEN` in Hemma `.env` + persistent HF cache mount (already in runbooks).

## Related

- `TASKS/assessment/offload-deberta--spacy-features-to-hemma-binary-embedding-service.md`
- `TASKS/programs/huledu_alpha_launch/hub.md`
- `docs/decisions/0025-hemma-hosted-nlp-feature-offload-for-essay-scoring-research-binary-protocol.md`
- `docs/operations/hemma-server-operations-huleedu.md`
- `docs/operations/ml-nlp-runbook.md`
