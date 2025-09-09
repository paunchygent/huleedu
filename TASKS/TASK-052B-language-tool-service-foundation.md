# TASK-052B — Language Tool Service Foundation ✅ COMPLETED

## Implementation Summary

Scaffolded HTTP service at port 8085 with Quart (not HuleEduApp - no DB requirement):

```python
# app.py (45 LoC < 150 limit)
app = Quart(__name__)
register_error_handlers(app)  # Rule 048
setup_correlation_middleware(app)  # Rule 043.2

# di.py - Dishka providers
CoreInfrastructureProvider: APP[Settings, CollectorRegistry, METRICS]
ServiceImplementationsProvider: APP[LanguageToolWrapperProtocol->StubLanguageToolWrapper]
RequestScopeProvider: REQUEST[CorrelationContext] from g.correlation_context

# protocols.py
async def check_text(text: str, correlation_id: UUID, language: str = "en-US") -> list[dict[str, Any]]
```

**Contract Separation (Critical Fix)**:

- **Inter-service**: `common_core/api_models/language_tool.py` - `GrammarCheckRequest/Response`
- **Intra-service**: `services/language_tool_service/api_models.py` - `LanguageToolRawResponse/Match`

**Tests**: 6 unit tests in `test_service_foundation.py` (all passing)

**Remaining**: Replace `StubLanguageToolWrapper` with Java integration (TASK-052C).