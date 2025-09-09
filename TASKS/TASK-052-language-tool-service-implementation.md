# 🧠 ULTRATHINK: TASK-052 — Language Tool Service (Revised)

## Executive Summary

- Purpose: Implement a stateless HTTP Language Tool Service that provides fine‑grained grammar categorization for NLP Phase 2. The service analyzes grammar only (spellchecked text in), returns categorized errors with full context for downstream analytics and feedback, and integrates with NLP via synchronous HTTP.
- Scope: Service scaffolding, Java LanguageTool wrapper, HTTP API, NLP client integration, observability, and containerization. Includes an explicit common_core event contract enhancement for richer grammar context.

## Linked Subtasks (split for independent teams)

- Subtask A — Common Core Contracts Update: TASKS/TASK-052A-contract-update-common-core.md
- Subtask B — Service Foundation & DI: TASKS/TASK-052B-language-tool-service-foundation.md
- Subtask C — Java Wrapper & Filtering: TASKS/TASK-052C-java-wrapper-integration.md
- Subtask D — HTTP API `/v1/check`: TASKS/TASK-052D-http-api-implementation.md
- Subtask E — NLP Client Integration & Resilience: TASKS/TASK-052E-nlp-service-integration.md
- Subtask F — Docker & Compose: TASKS/TASK-052F-dockerization-and-compose.md
- Subtask G — Observability & Health: TASKS/TASK-052G-observability-and-health.md

Each subtask is self‑contained with boundary objects, contracts, shared libraries, acceptance tests, and deliverables, per Rule 090.

## Architectural Alignment (Rules/Citations)

- HTTP Blueprint: 041-http-service-blueprint.mdc — `app.py` <150 LoC, `api/`, `protocols.py`, `di.py`, health blueprint.
- Async + DI: 042-async-patterns-and-di.mdc — Dishka scopes (APP stateless singletons, REQUEST instances), correlation DI pattern.
- EDA & Pipeline Flow: 037-phase2-processing-flow.mdc — BOS/ELS orchestrate services; Language Tool is not a pipeline participant.
- Proxy/HTTP Patterns: 042.2-http-proxy-service-patterns.mdc — correlation headers, error mapping, metrics for downstream calls.
- Result Aggregation: 020.12-result-aggregator-service-architecture.mdc — NLP events consumed by RAS; optional storage refs for richer JSON.
- Docs Standard: 090-documentation-standards.mdc — explicit contracts, env vars, examples, rule citations.

## Data Flow (High Level)

Spellchecker → Corrected Text → NLP Service
                                    ↓ (parallel)
                             spaCy metrics   +   Language Tool Service
                                    ↓                 (grammar categorization; grammar‑only)
                                    └──────────→ Combine → EssayNlpCompletedV1 → RAS → AI Feedback, BFF

## Contracts and Boundary Objects

- Events (common_core):
  - EssayNlpCompletedV1 (unchanged)
  - GrammarAnalysis (unchanged)
  - GrammarError (enhanced in Subtask A: add required context and category fields)
- HTTP (Language Tool Service):
  - POST `/v1/check` → Request: `{ text: str, language: "en"|"sv"|"auto" }`
  - Response: `{ errors: [...], total_grammar_errors: int, grammar_category_counts: dict, grammar_rule_counts: dict, language: str, processing_time_ms: int }`
  - Headers: `X-Correlation-ID` (required)
- Content Types (common_core.domain_enums):
  - Optional: store raw, rich grammar JSON as `ContentType.GRAMMAR_ANALYSIS_JSON` via Content Service (referenced by RAS/NLP if adopted).

## Key Constraints (confirmed)

- Grammar categorization only; no corrections or rewritten text.
- Input is spellchecked text from NLP; filter spelling categories server‑side.
- Output includes full error context (rule, category, offsets, context window).
- Pure HTTP microservice; stateless; no database.
- Data flows to AI Feedback and BFF via RAS aggregation.

## Phased Plan (Rule 090 compliant)

### Phase 0 — Architecture Study (read‑only)
- Goals: Align design with File Service and HTTP blueprint; confirm NLP touch‑points.
- References: 000-rule-index.mdc, 041, 042, 043.2, 084, services/file_service/*, services/nlp_service/*.
- Deliverable: Agreement on this doc and subtasks split.

### Phase 1 — Contracts Update (Subtask A)
- Objective: Enhance `GrammarError` with required fields to carry full error context.
- Changes (libs/common_core):
  - GrammarError: add `category_id: str`, `category_name: str`, `context: str`, `context_offset: int` (required; prototyping accepted).
  - Update model tests and any consumer serialization logic.
- Compatibility: NLP mapping updated in Subtask E; other services unaffected.
- Tests: Unit tests in common_core; contract tests where used.

### Phase 2 — Service Foundation & DI (Subtask B)
- Objective: Scaffold `services/language_tool_service` per 041.
- Structure: `app.py`, `api/health_routes.py`, `config.py`, `di.py`, `protocols.py`, `metrics.py`, `validation_models.py`.
- DI: APP scope wrapper provider; correlation middleware per 043.2.
- Tests: App startup, health endpoint, DI wiring.

### Phase 3 — Java Wrapper & Filtering (Subtask C)
- Objective: Implement LanguageTool Java process wrapper.
- Behavior: start/stop lifecycle, per‑request timeouts (≤30s), concurrency limits, OOM restart, and grammar‑only filtering (exclude TYPOS/MISSPELLING/SPELLING; optionally STYLE/TYPOGRAPHY if desired).
- Outputs: native LanguageTool matches mapped to enhanced GrammarError, plus counts (category/rule).
- Tests: wrapper happy‑path, timeout, OOM restart, filter correctness.

### Phase 4 — HTTP API `/v1/check` (Subtask D)
- Objective: Implement the grammar checking endpoint.
- Request model: `GrammarCheckRequest(text, language)`; validate length and language.
- Response model: `GrammarCheckResponse(errors, category/rule counts, language, processing_time_ms)`.
- Observability: `X-Correlation-ID` propagation; metrics for request/processing.
- Tests: contract tests, error mapping, correlation propagation.

### Phase 5 — NLP Integration & Resilience (Subtask E)
- Objective: Replace NLP `LanguageToolServiceClient` skeleton with real HTTP client.
- Behavior: POST `/v1/check`, map response to enhanced GrammarError/GrammarAnalysis; add circuit breaker and retry (044.1), timeouts, graceful degradations.
- Publishing: Continue sending EssayNlpCompletedV1; optionally include summarized counts in `processing_metadata` for analytics.
- Tests: integration test for BatchNlpAnalysisHandler calling service; resilience tests.

### Phase 6 — Docker & Compose (Subtask F)
- Objective: Production‑ready container with Java + Python.
- Pattern: 084-docker-containerization-standards.mdc; `PYTHONPATH=/app`, non‑root, PDM install; include LanguageTool artifacts or JRE install.
- Compose: Service definition, ports, env vars; no DB; health checks.
- Tests: build/run validation via `docker compose` and `/healthz`.

### Phase 7 — Observability & Health (Subtask G)
- Objective: Health endpoints, Prometheus metrics, structured logging, tracing context.
- Metrics: HTTP request totals, duration, downstream call metrics; wrapper latency.
- Health: `/healthz` includes JVM status + memory; `/metrics` exposed.
- Tests: metrics scrape; health JSON fields; logging includes correlation IDs.

## Implementation Notes & Decisions

- Filtering: MUST drop spelling/typo categories; publish only grammar categories. Maintain a documented category allow/deny list and tests.
- Rich Context: To keep events compact and compatible, publish enhanced GrammarError via EssayNlpCompletedV1. If richer context grows, store raw LanguageTool JSON via Content Service and include a storage reference (optional extension).
- Resilience: Implement circuit breaker and retries in NLP client; fall back to NLP metrics only if grammar service is down; emit error metadata.
- Documentation Drift: Update service docs (020.2, 037) to reflect that grammar analysis is obtained via Language Tool within NLP; Spellchecker remains spelling/correction only.

## Success Criteria

- Functional: grammar categorization only; full error context; English/Swedish; typically <2s; up to 10k words; grammar‑only filters applied.
- Architectural: pure HTTP; stateless; adheres to 041/042; integrates with NLP Phase 2; correlation/metrics in place.
- Operational: health/metrics endpoints; resilient NLP client; containers build and run under compose; restart‑safe.

## Risks & Mitigation

- JVM memory/latency spikes → bounded heap, concurrency limits, watchdog, timeouts.
- Contract fragmentation → centralize enhanced fields in common_core (Subtask A); keep event schema stable.
- Service unavailability → NLP graceful degradation; error reporting; retries with breaker.
- Container size → slim bases, multi‑stage build, cached layers.

## References

- Rules: 000, 041, 042, 042.2, 043, 043.2, 044.1, 070, 084, 090
- Templates: services/file_service/*
- Integration: services/nlp_service/implementations/language_tool_client_impl.py, command_handlers/batch_nlp_analysis_handler.py

Status: READY FOR IMPLEMENTATION  • Priority: HIGH  • Owner: NLP Platform Team

