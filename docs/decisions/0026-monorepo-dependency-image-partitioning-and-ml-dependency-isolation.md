---
type: decision
id: ADR-0026
status: proposed
created: '2026-02-01'
last_updated: '2026-02-01'
---
# ADR-0026: Monorepo dependency image partitioning and ML dependency isolation

## Status

Proposed

## Context

HuleEdu is a monorepo with multiple services and a shared dependency image strategy
(`Dockerfile.deps` + service images). This works well for a pure microservice backend,
but the project also contains rapidly evolving ML research dependencies (torch,
transformers, shap, spaCy models, sentence-transformers, etc.) which can make builds:

- slow (large wheels, GPU variants, heavy transitive deps)
- brittle (platform-specific GPU stacks)
- expensive in storage (multiple images duplicating large layers)

We want Hemma deployments to be as mature and efficient as Skriptoteket’s operational
workflow: “pull + compose up” with minimal rebuild time unless dependencies actually
changed.

We also want to preserve HuleEdu architecture constraints:
- services are isolated and do not “accidentally” gain ML deps
- research pipelines can iterate quickly without polluting production service images

## Decision

Adopt a **partitioned dependency strategy**:

1. Keep a **base service deps image** for core microservice runtime dependencies
   (Quart/FastAPI, Kafka, Redis, SQLAlchemy, common libs).
2. Create a separate **ML deps image** for GPU/ML workloads and the whitebox research
   pipeline (torch/transformers/spaCy/textdescriptives/shap/etc.).
3. Ensure production microservices only inherit from the base deps image unless the
   service explicitly requires ML inference at runtime.
4. For Hemma “feature offload” services (DeBERTa + spaCy), build from the ML deps image.
5. Keep dependency groups explicit in `pyproject.toml` and avoid implicit “install all
   groups everywhere”.

This ADR only commits to the *direction* and guardrails. The concrete implementation
details (image names, build scripts, caching, ROCm specifics) are handled in tasks.

## Consequences

### Positive

- Faster rebuilds for the majority of microservices.
- Smaller, more predictable production images.
- Clear boundary between research/ML stacks and production service stacks.
- Hemma deploy iteration becomes closer to Skriptoteket’s maturity level.

### Negative

- More build configuration complexity (multiple deps images).
- Requires careful documentation and CI alignment to prevent drift.

### Mitigations

- Make image selection explicit in compose/build scripts (no magic).
- Add a simple “which deps image does this service use?” reference table.
- Add CI checks to ensure ML deps do not leak into non-ML services.
