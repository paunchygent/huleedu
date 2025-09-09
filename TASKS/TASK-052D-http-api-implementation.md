# TASK-052D — HTTP API Implementation (`/v1/check`)

## Objective

Expose a POST `/v1/check` endpoint that accepts spellchecked text and returns grammar‑only categorization with full context and summary counts.

## Request/Response Models

```python
class GrammarCheckRequest(BaseModel):
    text: str
    language: Literal["en", "sv", "auto"]

class GrammarError(BaseModel):  # HTTP contract (mirrors common_core + context fields)
    rule_id: str
    message: str
    short_message: str
    offset: int
    length: int
    replacements: list[str]
    category: str
    severity: str
    category_id: str
    category_name: str
    context: str
    context_offset: int

class GrammarCheckResponse(BaseModel):
    errors: list[GrammarError]
    total_grammar_errors: int
    grammar_category_counts: dict[str, int]
    grammar_rule_counts: dict[str, int]
    language: str
    processing_time_ms: int
```

## Headers & Correlation

- Require and propagate `X-Correlation-ID` (Rule 043.2). Use middleware to populate DI correlation context.

## Error Handling

- Use `huleedu_service_libs.error_handling` to map validation errors (400), timeouts (504), wrapper failures (503) with correlation.

## Metrics

- `http_requests_total{method,endpoint,http_status}`
- `http_request_duration_seconds{method,endpoint}`
- `downstream_service_call_duration_seconds{service,method,endpoint}` (for wrapper if HTTP)

## Acceptance Tests

- Valid request returns expected structure with counts.
- Invalid language → 400; timeout → 504; wrapper failure → 503.
- Correlation id echoed via middleware (`corr.original`).

## Deliverables

- `api/grammar_routes.py` with contract validation, correlation, metrics, and structured errors.

