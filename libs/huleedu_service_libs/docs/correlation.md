# Correlation (HTTP + Events)

Purpose

- Normalize inbound correlation IDs at the HTTP boundary and use a canonical `UUID` internally while preserving the original string. Ensures consistent tracing across services and type safety for error/event APIs.

Components

- `error_handling/correlation.py`
  - `CorrelationContext`: `{ original: str, uuid: UUID, source: "header|query|generated" }`
  - `extract_correlation_context_from_request(request) -> CorrelationContext`
- `middleware/frameworks/quart_correlation_middleware.py`
  - `setup_correlation_middleware(app)`: attaches `g.correlation_context` and `g.correlation_id`

Quick Start (Quart)

```
from huleedu_service_libs.middleware.frameworks.quart_correlation_middleware import (
    setup_correlation_middleware,
)

app = Quart(__name__)
setup_correlation_middleware(app)  # early in app setup
```

DI (Dishka)

```
from dishka import provide, Scope
from huleedu_service_libs.error_handling.correlation import (
    CorrelationContext,
    extract_correlation_context_from_request,
)

@provide(scope=Scope.REQUEST)
def provide_correlation_context() -> CorrelationContext:
    from quart import g, request

    ctx = getattr(g, "correlation_context", None)
    if isinstance(ctx, CorrelationContext):
        return ctx
    return extract_correlation_context_from_request(request)
```

Usage

- Errors: `raise_*...(correlation_id=corr.uuid, original_correlation_id=corr.original, ...)`
- Success responses: return `corr.original` to clients
- Events: `envelope.correlation_id = corr.uuid`; optional: `metadata["original_correlation_id"] = corr.original`

Notes

- Canonicalization: If the inbound value is not a UUID, the library derives a deterministic `uuid5(NAMESPACE_OID, original)` to keep trace continuity.
- Metrics: Do not label metrics with correlation IDs (Rule 071.2). Keep correlation in logs and events.
- Tests: Use dependency injection to obtain `CorrelationContext` in route tests; do not reconstruct correlation in test helpers.
EOF
