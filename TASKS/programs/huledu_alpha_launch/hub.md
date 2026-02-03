---
id: 'hub'
title: 'HuleEdu alpha launch programme hub'
type: 'task'
status: 'in_progress'
priority: 'high'
domain: 'programs'
service: ''
owner_team: 'agents'
owner: ''
program: 'huledu_alpha_launch'
created: '2026-02-01'
last_updated: '2026-02-03'
related: ['docs/operations/hemma-server-operations-huleedu.md', 'docs/operations/gpu-ai-workloads-on-hemma-huleedu.md', 'docs/decisions/0025-hemma-hosted-nlp-feature-offload-for-essay-scoring-research-binary-protocol.md', 'docs/product/epics/ml-essay-scoring-pipeline.md', 'TASKS/assessment/nlp_lang_tool/nlp-lang-tool-whitebox-research-build.md', 'TASKS/assessment/offload-deberta--spacy-features-to-hemma-binary-embedding-service.md', 'TASKS/assessment/hemma-offload-combined-extract-endpoint.md']
labels: ['program', 'alpha', 'hemma', 'mvp']
---
# HuleEdu alpha launch programme hub

## Objective

Deliver a publicly reachable **alpha preview** of HuleEdu on Hemma with:
- end-to-end pipeline execution (upload → processing → results → BFF → frontend)
- controlled access (alpha testers + superadmin)
- a Hemma deployment workflow as mature and repeatable as Skriptoteket’s

This programme is also the anchor document to prevent context loss between sessions.

## Context

HuleEdu’s long-term purpose is to provide an AI-supported comparative judgement (CJ)
instrument as decision support for legitimate, equitable essay assessment, while
triangulating blackbox rankings against an interpretable “whitebox” model (XAI) and
explicit linguistic signals. The system must be usable in real teacher workflows
without collapsing writing competence into easy-to-measure proxies.

Near-term: ship an MVP that is operational, observable, and reproducible on Hemma.

## Milestones (programme-level)

M1. **Hemma platform readiness**
- DNS/TLS in place (public surface).
- Reverse proxy routing for HuleEdu domains.
- Shared network + shared-postgres availability (if used).

M2. **NLP predictor + XAI research MVP**
- Run the whitebox pipeline repeatably with offload plumbing:
  - `language_tool_service` on Hemma (Docker)
  - DeBERTa + spaCy/TextDescriptives offload service on Hemma (Docker)
  - binary embedding payloads for throughput
- Produce stable artifacts and evaluation outputs for review.

M3. **ENG5 + CJ full-scale readiness**
- Confirm token caching and inversion experiment conclusions.
- Run full-scale ranking (anchor + grade projections mode) reliably.

M4. **Full E2E microservice pipeline (HuleEdu)**
- Upload → register/parse → spellcheck → NLP analysis → CJ assessment → AI feedback →
  result aggregation → BFF → frontend.

M5. **Alpha preview launch**
- Controlled access gating in place.
- Observability + runbooks sufficient for daily operation.

## Workstreams

### Workstream A — Hemma deployment + HTTPS surface

Goal: make HuleEdu deploy on Hemma as “git pull + compose up” like Skriptoteket.

Key deliverables:
- A stable Hemma directory convention (to be chosen; do not assume one).
- HuleEdu attached to the same nginx-proxy/Let’s Encrypt patterns already used.
- Port discipline: only public entrypoints via `VIRTUAL_HOST`; everything else internal.

### Workstream B — NLP predictor + XAI pipeline (research)

Goal: complete the whitebox experiment work with maximum iteration speed by offloading
heavy runtime dependencies to Hemma.

Key deliverables:
- Remote feature extraction + local caching
- Binary protocol for embeddings
- Reproducible run metadata (config + git SHA + dataset path)
- Single combined extract endpoint (one tunnel, no local NLP fallbacks): `TASKS/assessment/hemma-offload-combined-extract-endpoint.md`

### Workstream C — CJ assessment + ENG5 full-scale

Goal: stabilize and validate the CJ side so the end-to-end pipeline can run at scale.

Key deliverables:
- Full-scale CJ runs reproducible on Hemma
- Token caching + cost controls verified
- Grade projection outputs coherent and explainable

### Workstream D — End-to-end pipeline + alpha UX

Goal: make the whole HuleEdu system run as a coherent product workflow.

Key deliverables:
- One “golden path” E2E runbook
- Alpha access gating + superadmin operations
- Minimal teacher UX (BFF + frontend) to view runs and results

## Day-by-day rollout sequence (Hemma)

This is an initial “day plan” for a ~10 day push. We can compress or expand as needed.

### Day 0 — Baseline and ground truth

Verify (Hemma):
- `hule-network` exists (external docker network)
- nginx-proxy stack is healthy and serving Skriptoteket
- `shared-postgres` reachable from `hule-network` (if used)

Verify (local):
- SSH access stable and non-root default
- tunnels work via autossh pattern

### Day 1 — DNS + TLS surface for HuleEdu

Outcome:
- HuleEdu domains resolve publicly and TLS cert issuance succeeds.

Verify:
- DNS A/AAAA records point to Hemma public IP.
- nginx-proxy routes:
  - `api.huleedu.hule.education` → API Gateway
  - `huleedu.hule.education` → BFF
  - `ws.huleedu.hule.education` → WebSocket service

### Day 2 — Hemma repo mirror + deploy workflow

Outcome:
- HuleEdu can be deployed on Hemma with a single, repeatable command sequence.

Verify:
- `git pull` works from Hemma repo location
- compose commands succeed (no interactive prompts)
- logs + health endpoints are reachable

### Day 3 — LanguageTool service (HuleEdu) on Hemma

Outcome:
- `language_tool_service` runs on Hemma and is reachable via tunnel for research.

Verify:
- Hemma: `curl http://127.0.0.1:8085/healthz`
- Local: autossh forward to `18085`, then `curl http://127.0.0.1:18085/healthz`
- Basic `POST /v1/check` succeeds for a short text

### Day 4 — DeBERTa + spaCy offload service (Docker)

Outcome:
- Offload service runs on Hemma and returns binary embeddings + spaCy features.

Verify:
- Local tunnel `19000` works and `/healthz` responds
- Embeddings payload decodes into a float32 matrix with expected shape
- Cold-cache and warm-cache latency measured and recorded

### Day 5 — Whitebox pipeline runs end-to-end with offload

Outcome:
- `pdm run essay-scoring-research ablation ...` runs locally with remote offload and
  produces artifacts quickly and repeatably.

Verify:
- Runs produce stable output directories under `output/essay_scoring/`
- Metadata includes offload configuration and versions
- No repeated model re-downloads if caches are mounted/working

### Day 6 — CJ readiness checkpoint (ENG5 full scale)

Outcome:
- Full-scale CJ workflow is runnable on Hemma (batch semantics, caching, projections).

Verify:
- smoke run passes
- token caching metrics and cost controls confirmed

### Day 7 — Full E2E microservice “golden path”

Outcome:
- A single end-to-end batch run completes and results are visible in the frontend.

Verify:
- upload works and is persisted
- downstream steps produce expected events and persisted states
- RAS + BFF return results

### Day 8 — Alpha gating and operational hardening

Outcome:
- only selected alpha testers can access the UI and API; superadmin workflows are
  documented.

Verify:
- auth gating behavior matches expectation
- “break glass” admin access documented
- observability dashboards support on-call debugging

### Day 9 — Alpha preview launch

Outcome:
- alpha invite flow is ready; monitoring and rollback procedures exist.

Verify:
- minimal smoke tests are run against public domains
- incident workflow is documented (who checks what, where logs live)

## Open Decisions / Unknowns

1. Hemma canonical repo location for HuleEdu (to be chosen).
2. Whether HuleEdu should share Skriptoteket’s nginx-proxy container and companion
   directly, or run its own proxy stack (default: share).
3. Whether Hemma should standardize on a non-snap Docker Engine install to avoid host
   mount restrictions from `/srv/scratch/...` (recommended: yes).
4. Monorepo dependency build strategy:
   - current deps-image approach vs splitting out ML dependencies into separate images
   - reducing “build everything all the time” behavior for server deploys

## Related

- `TASKS/infrastructure/hemma-operations-runbooks-huleedu--gpu.md`
- `TASKS/infrastructure/huleedu-devops-codex-skill-for-hemma-server.md`
- `TASKS/assessment/offload-deberta--spacy-features-to-hemma-binary-embedding-service.md`
- `docs/operations/hemma-alpha-rollout-days-1-3.md`

## Objective

[What are we trying to achieve?]

## Context

[Why is this needed?]

## Plan

[Key steps]

## Success Criteria

[How do we know it's done?]

## Related

[List related tasks or docs]
