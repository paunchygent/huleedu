# TASK-052E — NLP Client Integration & Resilience

## Objective

Replace the `LanguageToolServiceClient` skeleton with a production HTTP client that calls Language Tool Service, maps results to enhanced `GrammarError`, and adds resilience.

## Boundary Objects & Contracts

- Client method: `check_grammar(text: str, http_session: ClientSession, correlation_id: UUID, language: str = "auto") -> GrammarAnalysis`
- HTTP endpoint: `POST /v1/check` (see Subtask D)
- Events: `EssayNlpCompletedV1` includes `GrammarAnalysis`

## Shared Libraries

- `aiohttp.ClientSession` with timeouts
- `huleedu_service_libs.resilience.CircuitBreaker`
- `huleedu_service_libs.logging_utils` and `error_handling`

## Implementation Steps

1. Implement POST call with `X-Correlation-ID`, JSON payload, timeout.
2. On non‑200, raise structured external service error (service="language_tool_service").
3. Map HTTP response errors → enhanced `GrammarError` and build `GrammarAnalysis`.
4. Add a circuit breaker around the call and basic retry for transient failures.
5. Degrade gracefully: on breaker open or repeated failure, return `GrammarAnalysis(error_count=0, errors=[], language=detected)` and log.
6. In `BatchNlpAnalysisHandler`, optionally compute `grammar_category_counts`/`grammar_rule_counts` and include as `processing_metadata` in `EssayNlpCompletedV1` (non‑breaking enrichment).

## Acceptance Tests

- Integration test: NLP handler calls service and publishes events with grammar analysis.
- Resilience: simulate timeouts and 5xx → breaker trips; handler continues processing other essays.

## Deliverables

- Updated `services/nlp_service/implementations/language_tool_client_impl.py` with real HTTP logic.
- Unit + integration tests in NLP service.

