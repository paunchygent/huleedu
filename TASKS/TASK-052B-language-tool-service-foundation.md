# TASK-052B — Language Tool Service Foundation & DI

## Objective

Scaffold `services/language_tool_service` as a pure HTTP microservice per 041, with DI, correlation middleware, and health endpoint.

## Directory Structure

```
services/language_tool_service/
├── app.py                 # Quart app (<150 LoC)
├── config.py              # Pydantic settings (env_prefix)
├── di.py                  # Dishka providers (APP scope wrapper)
├── protocols.py           # LanguageToolWrapperProtocol
├── metrics.py             # Prometheus registry/metrics
├── validation_models.py   # Request/response pydantic models
└── api/
    ├── __init__.py
    └── health_routes.py   # /healthz & /metrics
```

## Boundary Objects & Contracts

- Protocols: `LanguageToolWrapperProtocol.check_text(text: str, language: str) -> list[GrammarError]`
- HTTP: `GET /healthz` JSON; `GET /metrics` Prometheus exposition
- DI scopes: APP (wrapper, metrics); REQUEST (correlation context)

## Shared Libraries

- `huleedu_service_libs.middleware.frameworks.quart_correlation_middleware`
- `prometheus_client` (Rule 071.x)
- `dishka` (Rule 042)

## Implementation Steps

1. Create `app.py` and register health blueprint.
2. Configure correlation middleware early (Rule 043.2).
3. Provide DI container in `di.py` with APP scope providers (metrics, wrapper placeholder).
4. Implement `config.py` with `env_prefix`, `HTTP_PORT` (8085) and wrapper config (heap, timeouts, mode).
5. Implement `health_routes.py` returning service up + JVM status placeholder.

## Acceptance Tests

- App boots; `/healthz` returns 200 JSON; `/metrics` scrapes.
- DI resolves providers; correlation context available in request scope.

## Deliverables

- Service skeleton in repo; running health endpoint locally.

