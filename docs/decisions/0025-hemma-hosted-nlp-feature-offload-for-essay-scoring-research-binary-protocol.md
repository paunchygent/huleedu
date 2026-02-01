---
type: decision
id: ADR-0025
status: proposed
created: '2026-02-01'
last_updated: '2026-02-01'
---
# ADR-0025: Hemma-hosted NLP feature offload for essay-scoring research (binary protocol)

## Status

Proposed

## Context

The whitebox essay-scoring research pipeline currently extracts:
- DeBERTa-v3-base embeddings (GPU/RAM heavy)
- spaCy + TextDescriptives features (CPU/RAM heavy)
- LanguageTool error counts (Java server)

We want the local iteration loop (MacBook) to remain snappy by offloading all heavy NLP
runtime dependencies (GPU + large RAM processes) onto the Hemma server, while still
keeping training/evaluation logic easy to iterate on locally.

This also supports a broader long-term goal: Skriptoteket can reuse HuleEdu backend
processing services (LanguageTool, NLP Service, future AI feedback service) as shared
infrastructure behind SSO.

## Decision

### 1) Run HuleEdu `language_tool_service` on Hemma (Docker)

- Deploy `services/language_tool_service` on Hemma via Docker.
- Bind the HTTP API to localhost on Hemma and expose it to the Mac via a tunnel.
- Clients call the HuleEdu API `POST /v1/check` (not the underlying Java port).

### 2) Add a Hemma “feature offload” service for DeBERTa + spaCy (Docker)

Implement a small HTTP service on Hemma that performs:
- DeBERTa-v3-base embedding extraction with CLS pooling
- spaCy/TextDescriptives feature extraction needed by the research pipeline

The Mac research pipeline becomes an orchestrator:
- fetch remote features (over tunnel)
- persist disk caches locally
- train/evaluate XGBoost locally

Operational default (Hemma GPU):
- Use `rocm/pytorch:latest` as the base image for the offload container to ensure ROCm runtime compatibility.
- Ensure the build does not overwrite the base image’s ROCm-enabled `torch` wheel.

### 3) Use a binary response format for embeddings

To avoid JSON float-array overhead, the embedding endpoint returns a binary payload.
The contract is:
- Request: JSON (`application/json`) containing `texts`, model config, and options.
- Response: `application/octet-stream` containing a NumPy `.npy` payload
  (`float32` matrix shaped `[batch, 768]` for DeBERTa-v3-base).

Rationale:
- high throughput and low CPU overhead on both ends
- simple, robust decoding in Python via NumPy

### 4) Default transport: SSH local port forwards

Use SSH local port forwarding for safety and simplicity. The existing tunnel method
(used for llama.cpp) remains an explicit alternative for comparison.

## Consequences

### Positive

- Local machine stays light: no GPU/Java server/spaCy heavy runtime.
- Faster iteration with stable disk caching and a consistent remote runtime.
- Clear service boundaries that are compatible with future Skriptoteket→HuleEdu reuse.

### Negative

- More moving parts: additional container(s) and health monitoring on Hemma.
- Network dependency: feature extraction now depends on tunnel availability/latency.
- Contract versioning becomes important (binary payload must be strictly defined).

### Mitigations

- Bind services to localhost on Hemma and require tunnels for access.
- Add health endpoints and strict request/response validation.
- Version the offload API (path and/or explicit `api_version`) and record it in
  research metadata for reproducibility.
