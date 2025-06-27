---
description: Defines concise FastAPI integration patterns for client-facing services, ensuring compliance with HuleEdu's core architecture.
globs: []
alwaysApply: false
---
# 041: FastAPI Integration Patterns

## 1. Overview

This rule provides patterns for building client-facing services with FastAPI. FastAPI is an approved exception for services that directly support the React frontend, due to its robust tooling and OpenAPI generation. All internal services **MUST** use Quart.

**Key Principles**:
-   **DI First**: Use Dishka for dependency injection, consistent with other services.
-   **Service Libs**: Integrate standard HuleEdu libraries for Kafka, logging, and metrics.
-   **Clear Contracts**: Define explicit Pydantic models for all requests, responses, and errors.
-   **Testability**: Ensure dependencies can be easily mocked for testing.

## 2. Core Structure & Integration

### 2.1. Directory Structure

A typical FastAPI service follows this layout:

```
services/<fastapi_service>/
├── main.py                 # App creation and setup
├── startup_setup.py        # DI, middleware, metrics
├── routers/
│   ├── health_routes.py
│   └── <domain>_routes.py
├── models/
│   ├── requests.py
│   └── responses.py
├── protocols.py            # Behavioral contracts (Protocols)
├── implementations/
│   └── <protocol>_impl.py
├── di.py                   # Dishka providers
├── config.py
└── tests/
```

### 2.2. Application Setup (`main.py`)

The entrypoint configures DI, middleware, and routers.

```python
# main.py
from fastapi import FastAPI
from dishka.integrations.fastapi import setup_dishka
from .startup_setup import create_di_container
from .routers import health_router, domain_router

app = FastAPI(title="Client-Facing Service")

# 1. Create and set up DI container
container = create_di_container()
setup_dishka(container, app)

# 2. Add middleware (e.g., CORS)
app.add_middleware(...)

# 3. Register routers
app.include_router(health_router)
app.include_router(domain_router, prefix="/v1")

# 4. Add startup/shutdown logic
@app.on_event("shutdown")
async def shutdown():
    await container.close()
```

### 2.3. Dependency Injection (`di.py`)

Use Dishka providers to manage dependencies like database connections, Kafka clients, and other services.

```python
# di.py
from dishka import Provider, Scope, provide
from huleedu_service_libs.kafka_client import KafkaBus
from .protocols import EventPublisherProtocol
from .implementations import DefaultEventPublisher

class FastAPIServiceProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_kafka_bus(self, settings: Settings) -> KafkaBus:
        # ... setup and return KafkaBus instance
    
    @provide(scope=Scope.REQUEST)
    def provide_event_publisher(self, kafka_bus: KafkaBus) -> EventPublisherProtocol:
        return DefaultEventPublisher(kafka_bus)
```

### 2.4. Routers & Endpoints

Use `APIRouter` to group related endpoints. Inject dependencies using `FromDishka`.

```python
# routers/health_routes.py
from fastapi import APIRouter
from dishka.integrations.fastapi import FromDishka
from prometheus_client import CollectorRegistry, generate_latest

health_router = APIRouter(tags=["Health"])

@health_router.get("/metrics")
async def metrics(registry: FromDishka[CollectorRegistry]):
    return PlainTextResponse(generate_latest(registry))
```

## 3. Frontend Integration (React)

### 3.1. CORS

CORS **MUST** be configured to allow requests from the React frontend's origins.

```python
# main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS, # e.g., ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 3.2. Pydantic Models

Use clear Pydantic models for all API boundaries.

```python
# models/requests.py
from pydantic import BaseModel, Field

class PipelineRequest(BaseModel):
    batch_id: str = Field(..., min_length=1)
    pipeline_name: str

# models/responses.py
class AcceptedResponse(BaseModel):
    message: str
    correlation_id: str
    status: str = "accepted"
```

## 4. Observability Integration

### 4.1. Metrics Implementation
**MUST** implement comprehensive metrics following established patterns:

```python
# app/metrics.py
from prometheus_client import Counter, Histogram

class ServiceMetrics:
    def __init__(self) -> None:
        self.http_requests_total = Counter(
            "service_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "http_status"]
        )
        self.http_request_duration_seconds = Histogram(
            "service_http_request_duration_seconds", 
            "HTTP request duration",
            ["method", "endpoint"]
        )

# di.py
@provide(scope=Scope.APP)
def provide_metrics(self) -> ServiceMetrics:
    return ServiceMetrics()

@provide(scope=Scope.APP) 
def provide_registry(self) -> CollectorRegistry:
    return REGISTRY
```

### 4.2. Health and Metrics Endpoints
**MUST** provide standard observability endpoints:

```python
# routers/health_routes.py
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

router = APIRouter(tags=["Health"])

@router.get("/healthz")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "message": "Service is healthy"}

@router.get("/metrics")
@inject
async def metrics(registry: FromDishka[CollectorRegistry]) -> PlainTextResponse:
    metrics_data = generate_latest(registry)
    return PlainTextResponse(content=metrics_data, media_type=CONTENT_TYPE_LATEST)
```

### 4.3. Route Instrumentation
**MUST** instrument all routes with metrics:

```python
@router.post("/endpoint")
@inject
async def handler(
    metrics: FromDishka[ServiceMetrics],
    # other dependencies
):
    endpoint = "/endpoint"
    with metrics.http_request_duration_seconds.labels(method="POST", endpoint=endpoint).time():
        try:
            # ... business logic ...
            metrics.http_requests_total.labels(method="POST", endpoint=endpoint, http_status="200").inc()
            return result
        except HTTPException:
            raise  # Let FastAPI handle HTTP exceptions
        except Exception as e:
            metrics.http_requests_total.labels(method="POST", endpoint=endpoint, http_status="500").inc()
            raise HTTPException(status_code=500, detail="Internal server error") from e
```

## 5. Testing

### 5.1. Test Provider Setup
**MUST** include metrics providers in test setup and clear registry between tests:

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from dishka import make_async_container
from prometheus_client import CollectorRegistry

class MockProvider(Provider):
    @provide
    def provide_metrics(self) -> ServiceMetrics:
        return ServiceMetrics()
    
    @provide
    def provide_registry(self) -> CollectorRegistry:
        from prometheus_client import REGISTRY
        return REGISTRY

@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    """Clear Prometheus registry before each test to avoid collisions."""
    from prometheus_client import REGISTRY
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield

@pytest.fixture
async def client():
    container = make_async_container(MockProvider())
    # ... setup test client with container
    yield client
    await container.close()
```

### 5.2. Integration Testing
Use `respx` for mocking downstream HTTP services:

```python
@pytest.mark.asyncio
async def test_proxy_endpoint(client: AsyncClient, respx_mock: MockRouter):
    downstream_url = "http://downstream_service:8000/api/endpoint"
    mock_route = respx_mock.get(downstream_url).mock(
        return_value=Response(200, json={"result": "success"})
    )
    
    response = await client.get("/v1/proxy/endpoint")
    
    assert response.status_code == 200
    assert mock_route.called
```

## 5. Compliance Summary

-   **Framework**: FastAPI for client-facing, Quart for internal.
-   **DI**: Dishka with `Provider` classes.
-   **Libraries**: Use `huleedu_service_libs` for Kafka and logging.
-   **Contracts**: Use `typing.Protocol` for business logic interfaces.
-   **Models**: Strict Pydantic models for requests/responses.
-   **Deployment**: Use Uvicorn and provide a `/healthz` endpoint.
