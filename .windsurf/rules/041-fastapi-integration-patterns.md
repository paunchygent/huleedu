---
description: FastAPI integration patterns for client-facing services with HuleEdu architecture compliance
globs: []
alwaysApply: false
---
# 041: FastAPI Integration Patterns

## Overview

FastAPI is approved ONLY for client-facing services that directly support React frontend. All internal services **MUST** use Quart.

**Key Requirements:**
- **DI First**: Use Dishka for dependency injection
- **Service Libs**: Integrate standard HuleEdu libraries (Kafka, logging, metrics)  
- **Clear Contracts**: Explicit Pydantic models for requests/responses/errors
- **Testability**: Dependencies easily mocked for testing

## Core Structure

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
├── protocols.py            # Behavioral contracts
├── implementations/
├── di.py                   # Dishka providers
├── config.py
└── tests/
```

## Application Setup

```python
# main.py
from fastapi import FastAPI
from dishka.integrations.fastapi import setup_dishka
from .startup_setup import create_di_container

app = FastAPI(title="Service Name", version="1.0.0")

@app.on_event("startup")
async def startup():
    container = create_di_container()
    setup_dishka(container, app)

# startup_setup.py
from dishka import make_async_container
from huleedu_service_libs.observability import setup_observability

def create_di_container():
    container = make_async_container(ServiceProvider())
    setup_observability(container)
    return container
```

## Router Patterns

```python
# routers/domain_routes.py
from fastapi import APIRouter, Depends
from dishka.integrations.fastapi import FromDishka

router = APIRouter(prefix="/api/v1", tags=["domain"])

@router.post("/endpoint", response_model=ResponseModel)
async def create_resource(
    request: RequestModel,
    service: FromDishka[ServiceProtocol],
) -> ResponseModel:
    result = await service.process(request)
    return ResponseModel.from_domain(result)

@router.get("/endpoint/{resource_id}")
async def get_resource(
    resource_id: str,
    service: FromDishka[ServiceProtocol],
) -> ResponseModel:
    result = await service.get_by_id(resource_id)
    if not result:
        raise HTTPException(status_code=404, detail="Resource not found")
    return ResponseModel.from_domain(result)
```

## Error Handling

```python
# Custom exception handlers
from fastapi import HTTPException
from fastapi.responses import JSONResponse

@app.exception_handler(ValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "errors": exc.errors()}
    )

@app.exception_handler(DomainError)
async def domain_exception_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "error_code": exc.error_code}
    )
```

## Frontend Integration (React)

```python
# CORS configuration for React frontend
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Response models for frontend consumption
class StudentResponse(BaseModel):
    id: str
    name: str
    email: str
    created_at: datetime
    
    @classmethod
    def from_domain(cls, student: Student) -> "StudentResponse":
        return cls(
            id=str(student.id),
            name=student.full_name,
            email=student.email,
            created_at=student.created_at
        )
```

## Observability Integration

```python
# Metrics integration
from huleedu_service_libs.observability import create_service_metrics
from prometheus_client import generate_latest

@app.on_event("startup")
async def setup_metrics():
    app.state.metrics = create_service_metrics("service_name")

@app.get("/metrics")
async def get_metrics():
    return Response(generate_latest(), media_type="text/plain")

# Distributed tracing
from huleedu_service_libs.observability import trace_request

@router.post("/endpoint")
@trace_request("endpoint_operation")
async def traced_endpoint(
    request: RequestModel,
    service: FromDishka[ServiceProtocol],
):
    return await service.process(request)
```

## Health Endpoints

```python
# routers/health_routes.py
from fastapi import APIRouter
from huleedu_service_libs.database import DatabaseHealthChecker

health_router = APIRouter(tags=["health"])

@health_router.get("/healthz")
async def health_check():
    return {
        "service": "service_name",
        "status": "healthy",
        "environment": settings.ENVIRONMENT.value,
    }

@health_router.get("/healthz/database")
async def database_health(
    health_checker: FromDishka[DatabaseHealthChecker],
):
    health_data = await health_checker.check_detailed_health()
    status_code = 200 if health_data["healthy"] else 503
    return Response(
        content=json.dumps(health_data),
        status_code=status_code,
        media_type="application/json"
    )
```

## Testing Patterns

```python
# tests/conftest.py
import pytest
from dishka import make_async_container
from fastapi.testclient import TestClient

@pytest.fixture
def test_container():
    """Test DI container with mocked dependencies."""
    return make_async_container(TestServiceProvider())

@pytest.fixture
def client(test_container):
    """FastAPI test client with test container."""
    app.dependency_overrides[get_container] = lambda: test_container
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

# tests/test_api.py
def test_create_resource(client, mock_service):
    response = client.post("/api/v1/endpoint", json={"name": "test"})
    assert response.status_code == 201
    mock_service.process.assert_called_once()
```

## DI Provider Pattern

```python
# di.py
from dishka import Provider, provide, Scope
from huleedu_service_libs import RedisClient, KafkaBus

class ServiceProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> RedisClientProtocol:
        client = RedisClient(client_id="service", redis_url=settings.REDIS_URL)
        await client.start()
        return client
    
    @provide(scope=Scope.APP)  
    async def provide_kafka_bus(self, settings: Settings) -> KafkaPublisherProtocol:
        bus = KafkaBus(client_id="service", bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
        await bus.start()
        return bus
    
    @provide(scope=Scope.REQUEST)
    async def provide_service(
        self,
        repository: RepositoryProtocol,
        publisher: EventPublisherProtocol,
    ) -> ServiceProtocol:
        return ServiceImpl(repository, publisher)
```

## Compliance Requirements

1. **DI Framework**: MUST use Dishka for all dependencies
2. **Service Libraries**: MUST use HuleEdu service libraries for infrastructure
3. **Protocol Contracts**: MUST define behavioral contracts using `typing.Protocol`
4. **Error Handling**: MUST implement custom exception handlers for domain errors
5. **Observability**: MUST integrate metrics, tracing, and health endpoints
6. **Testing**: MUST support dependency injection in tests with mocked protocols
