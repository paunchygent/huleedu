# 🧠 ULTRATHINK: TASK-052 — Language Tool Service (IN PROGRESS)

## Executive Summary

- Purpose: Implement a stateless HTTP Language Tool Service that provides fine‑grained grammar categorization for NLP Phase 2. The service analyzes grammar only (spellchecked text in), returns categorized errors with full context for downstream analytics and feedback, and integrates with NLP via synchronous HTTP.
- Scope: Service scaffolding, Java LanguageTool wrapper, HTTP API, NLP client integration, observability, and containerization. Includes an explicit common_core event contract enhancement for richer grammar context.

## Current Status

**Completed (5/7 subtasks)**:

- ✅ **TASK-052A**: GrammarError enhanced with 4 context fields (`category_id`, `category_name`, `context`, `context_offset`)
- ✅ **TASK-052B**: Service foundation scaffolded (port 8085, Quart, DI, health endpoints, correlation middleware)
- ✅ **TASK-052C**: Java wrapper & filtering implemented (process lifecycle, grammar filtering, 299 unit tests)
- ✅ **TASK-052D**: HTTP API `/v1/check` implemented (word-based metrics, 366 tests passing, 100% coverage)
- ✅ **TASK-052F (Part 1)**: Docker & Service Startup - containerization files created (Dockerfile, docker-compose entries)

**Critical Architectural Decisions**:

- Inter-service contracts in `common_core/api_models/language_tool.py` (prevents service coupling)
- Plain Quart (not HuleEduApp) - no database requirement
- Stub implementation ready for Java wrapper replacement

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

### Phase 0 — Architecture Study ✅ COMPLETED

- Analyzed File Service patterns, DI architecture, correlation middleware integration
- Confirmed plain Quart pattern (no HuleEduApp) for stateless services

### Phase 1 — Contracts Update (Subtask A) ✅ COMPLETED  

- Enhanced `GrammarError` with 4 required fields in `libs/common_core/src/common_core/events/nlp_events.py:192-199`
- 7 unit tests passing in `test_grammar_models.py`
- NLP mocks updated with context extraction logic

### Phase 2 — Service Foundation & DI (Subtask B) ✅ COMPLETED

- Service scaffolded at port 8085 with Quart, Dishka DI, correlation middleware
- Inter-service contracts in `common_core/api_models/language_tool.py`
- 6 unit tests passing; stub wrapper provides predictable responses

### Phase 3 — Java Wrapper & Filtering (Subtask C) ✅ COMPLETED

Implemented `LanguageToolManager` (subprocess lifecycle, health checks, exponential backoff), `LanguageToolWrapper` (grammar filtering, category exclusion), `StubWrapper` (JAR-absent fallback). 299 unit tests, Rule 075 compliant (no @patch, <500 LoC/file). Integration tests documented for subprocess/signal handling.

### Phase 4 — HTTP API `/v1/check` (Subtask D) ✅ COMPLETED

- Implemented `/v1/check` endpoint with full DI integration (Dishka)
- Request validation with `GrammarCheckRequest(text, language)` - accepts "en-US", "sv-SE", "auto"
- Response includes categorized errors, word-based metrics (0-100, 101-250, 251-500, 501-1000, 1001-2000, 2000+ words)
- 366 unit tests passing; reorganized into 6 focused test files (<300 LoC each, Rule 075 compliant)
- Fixed: language pattern to accept "auto", test infrastructure for Dishka mocking, processing time calculation

### Phase 5 — Docker & Service Startup (Subtask F - Part 1) ✅ COMPLETED

Created containerization files following established patterns:
- `pyproject.toml` - PDM configuration without version pinning
- `hypercorn_config.py` - Service startup configuration (port 8085)
- `Dockerfile` - Multi-stage build with Java 17 + Python 3.11
- `Dockerfile.dev` - Development image with hot-reload support
- `docker-compose.services.yml` - Added language_tool_service entry
- `docker-compose.dev.yml` - Added development overrides

### Phase 6 — NLP Integration & Resilience (Subtask E)

### Phase 6 — Docker & Compose (Subtask F - Part 2)

- Complete docker-compose integration
- Verify health checks and service discovery
- Test container networking and Kafka connectivity
- Validate JAR loading and Java process management

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

Status: IN PROGRESS (5/7 subtasks complete)  • Priority: HIGH  • Owner: NLP Platform Team

## Pattern Requirements

Validated patterns from existing services:
- Use `hypercorn_config.py` (not main.py)
- No version pinning in dependencies
- Multi-stage Docker builds
- Java 17 required in Docker image
