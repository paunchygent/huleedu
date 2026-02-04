---
id: 'optimize-hemma-offload-throughput'
title: 'optimize hemma offload throughput'
type: 'task'
status: 'in_progress'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-04'
last_updated: '2026-02-04'
related: []
labels: []
---
# optimize hemma offload throughput

## Objective

Increase end-to-end feature extraction throughput for ELLIPSE (`feature_set=combined`) when
running with Hemma offload, without reducing feature quality (no smaller embeddings / no feature
skips), and without increasing client request timeouts.

## Context

Current Hemma `/v1/extract` throughput is primarily limited by CPU-heavy Tier1 (LanguageTool) and
Tier2 (spaCy parsing + DeBERTa embeddings). Client-side timeouts can occur when a single 64-item
batch exceeds the 60s request timeout. We want:

- Continuous, progress-oriented logs (not per-essay spam).
- Higher throughput by scaling CPU/GPU utilization (esp. LanguageTool CPU and DeBERTa GPU).
- Stability under sustained load (avoid host watchdog resets / non-essential GPU consumers).

## Plan

- Tune Hemma services for load: LanguageTool concurrency + JVM heap; offload batch size.
- Add safe concurrency in the combined offload server:
  - Multiple worker threads for concurrent `/v1/extract` computations.
  - Serialize GPU embedder access to avoid VRAM contention.
  - Cap total in-flight LanguageTool HTTP requests via a global semaphore.
  - Avoid cross-thread spaCy usage via a pool of per-worker spaCy pipelines.
- Add client-side in-flight concurrency for missing-record fetches (bounded, preserves ordering).
- Measure throughput and resource utilization (CPU/RAM/GPU) during load and adjust knobs.
- Document the chosen defaults + knobs in Hemma runbooks (if needed).

## Success Criteria

- ELLIPSE full run completes feature extraction without timeouts at `request_timeout_s=60`.
- Sustained throughput improves vs baseline and produces progress logs (batch-level ETA/rate).
- Hemma GPU and CPU are meaningfully utilized during extraction, with safe RAM/VRAM headroom.

## Update (2026-02-04): Completed full run (Hemma backend, combined)

Run:
- run name: `ellipse_full_hemma_20260204_071238`
- output: `output/essay_scoring/20260204_061242_ellipse_full_hemma_20260204_071238/`

Model metrics (QWK; `artifacts/metrics.json`):
- train: `0.99295`
- val: `0.64241`
- test: `0.65552`

Offload throughput + stability (`artifacts/offload_metrics.json`):
- total feature extraction: `4.04 essays/s` (`6168` essays in `1525.40s`)
- `/v1/extract` requests: `97` total, `97` ok, `0` timeouts
- request latency: mean `31.19s`, p95 `34.05s`, p99 `45.66s`

Interpretation (actionable):
- The run meets the “no timeouts at 60s” stability goal with meaningful throughput.
- Per-request throughput is ~`63.34 / 31.19 ≈ 2.03` essays/s; headline ~`4.04` essays/s implies
  ~2 concurrent `/v1/extract` computations were sustained end-to-end.
- Next throughput gains likely require more CPU for LanguageTool and/or higher LanguageTool
  concurrency (then match offload concurrency), not larger client timeouts.

## Next Steps

- Measure Hemma saturation during extraction:
  - CPU/RAM: `sudo docker stats`
  - GPU: `rocm-smi`
- If CPU headroom exists, scale LanguageTool first:
  - `LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS`
  - `WEB_CONCURRENCY` (Hypercorn workers; increases RAM)
  - `LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_HEAP_SIZE` (reduce GC pressure)
- Match offload concurrency to LanguageTool capacity:
  - `OFFLOAD_LANGUAGE_TOOL_MAX_CONCURRENCY`
  - `OFFLOAD_HTTP_MAX_WORKERS`

## Related

- `docs/decisions/0025-hemma-hosted-nlp-feature-offload-for-essay-scoring-research-binary-protocol.md`
- `docs/operations/hemma-server-operations-huleedu.md`
- `docs/operations/gpu-ai-workloads-on-hemma-huleedu.md`
