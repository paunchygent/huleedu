---
id: offload-deberta--spacy-features-to-hemma-binary-embedding-service
title: Offload DeBERTa + spaCy features to Hemma (binary embedding service)
type: task
status: in_progress
priority: high
domain: assessment
service: nlp_service
owner_team: agents
owner: ''
program: ''
created: '2026-02-01'
last_updated: '2026-02-03'
related:
- TASKS/assessment/hemma-offload-combined-extract-endpoint.md
labels:
- essay-scoring
- whitebox
- deberta
- spacy
- hemma
- binary-protocol
---
# Offload DeBERTa + spaCy features to Hemma (binary embedding service)

## Objective

Enable fast local iteration of the whitebox essay scoring research pipeline by
offloading RAM/GPU-heavy feature extraction to Hemma:
- DeBERTa-v3-base embeddings (GPU-backed)
- spaCy + TextDescriptives-derived features (CPU-heavy, high-RAM)

The Mac orchestrates experiments and trains XGBoost locally using cached, deterministic
feature outputs.

## Context

The current research pipeline computes DeBERTa embeddings locally via transformers/torch
(`scripts/ml_training/essay_scoring/features/embeddings.py`), and Tier 1/2 features use
spaCy/TextDescriptives locally (`scripts/ml_training/essay_scoring/features/pipeline.py`).

We want to keep the local laptop loop snappy and predictable by moving all heavy model
and NLP runtime dependencies into Hemma Docker containers, reachable via localhost-only
ports and tunnels.

This also aligns with the long-term direction where Skriptoteket can reuse HuleEdu
backend processing services (LanguageTool, NLP Service, future AI feedback service).

## Plan

1. Define the HTTP contract for a Hemma “feature offload service” (binary response for
   throughput).
2. Implement and dockerize the service on Hemma (GPU-enabled container).
3. Update the research pipeline to support:
   - `local` backend (current behavior)
   - `remote` backend (calls Hemma services)
4. Add deterministic, disk-backed caching on the Mac keyed by:
   - model/version + config (max_length, pooling)
   - stable hash of essay text (and prompt where relevant)
5. Measure and compare:
   - end-to-end wall time for `ablation`
   - cold-cache vs warm-cache performance
   - SSH port-forward vs existing tunnel method

## Current Implementation (2026-02-01)

Implemented the first, embedding-focused slice end-to-end:

- Hemma embedding offload server (binary `.npy` response):
  - `scripts/ml_training/essay_scoring/offload/server.py`
  - `scripts/ml_training/essay_scoring/offload/Dockerfile`
  - API:
    - `GET /healthz`
    - `POST /v1/embed` → `.npy` float32 matrix
- Research pipeline wiring:
  - `scripts/ml_training/essay_scoring/config.py` adds `OffloadConfig`
  - `scripts/ml_training/essay_scoring/features/pipeline.py` selects remote embedding client when configured
  - `scripts/ml_training/essay_scoring/features/tier1_error_readability.py` can call Hemma `language_tool_service` when configured
  - CLI flags:
    - `--embedding-service-url http://127.0.0.1:19000`
    - `--language-tool-service-url http://127.0.0.1:18085`
- Mac-side disk cache for embeddings:
  - `scripts/ml_training/essay_scoring/offload/embedding_client.py`

Runbook updates:
- `docs/operations/hemma-alpha-rollout-days-1-3.md`
- `docs/operations/hemma-server-operations-huleedu.md`
- `docs/operations/gpu-ai-workloads-on-hemma-huleedu.md`

Dependency isolation (Hemma runtime images):
- Added a dedicated `offload-runtime` dependency group (no training deps like XGBoost/SHAP).
- Updated the offload Dockerfile to export only `offload-runtime` with `pdm export --no-default`.
- Updated `hemma_offload_deploy.sh` to avoid hardcoding `/snap/bin/docker` and to adapt cache
  mounts when docker-snap is detected.

Hemma validation (2026-02-01):
- `language_tool_service` is running and healthy on Hemma, bound to `127.0.0.1:8085`.
- Embedding offload is running and healthy on Hemma, bound to `127.0.0.1:9000`.
- Mac-side tunnels validated for both endpoints (ports `18085` and `19000`).
- Note: set `HF_TOKEN` in `~/apps/huleedu/.env` on Hemma to avoid Hugging Face Hub rate limiting.

Still TODO (next slices):
- Implement a single combined `/v1/extract` endpoint that returns embeddings + Tier1/2/3 features
  and calls `language_tool_service` internally (zero local fallbacks). See:
  `TASKS/assessment/hemma-offload-combined-extract-endpoint.md`.
- Canonical ROCm base image: `rocm/pytorch:latest` (avoid pip overwriting `torch` during build).

## Success Criteria

- Remote feature extraction is selectable via config and works end-to-end.
- Remote responses are binary (no JSON float arrays for embeddings).
- Disk cache makes repeated runs fast even when Hemma is busy/offline.
- A documented tunnel setup exists for both LanguageTool and the feature service.

## Related

- `docs/decisions/0025-hemma-hosted-nlp-feature-offload-for-essay-scoring-research-binary-protocol.md`
- `docs/operations/hemma-server-operations-huleedu.md`
- `docs/operations/gpu-ai-workloads-on-hemma-huleedu.md`
- `TASKS/assessment/nlp_lang_tool/nlp-lang-tool-whitebox-research-build.md`
