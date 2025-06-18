---
description: Defines FastAPI integration patterns with service library compliance for client-facing services.
globs: 
alwaysApply: false
---
# 041: FastAPI Integration Patterns

## 1. Purpose

Defines FastAPI integration patterns with service library compliance for client-facing services.

**Context**: Architectural exception for client-facing services where FastAPI provides superior React frontend integration capabilities.

**Related Rules**:

- [040-service-implementation-guidelines.mdc](mdc:040-service-implementation-guidelines.mdc) - Core service guidelines
- [042-async-patterns-and-di.mdc](mdc:042-async-patterns-and-di.mdc) - Dependency injection patterns

## 2. FastAPI Service Structure

### 2.1. Directory Structure

```
services/<fastapi_service>/
├── main.py                       # FastAPI app creation and setup
├── startup_setup.py              # DI + middleware + metrics initialization
├── routers/
│   ├── __init__.py
│   ├── health_routes.py          # /healthz, /metrics, /docs endpoints
│   └── <domain>_routes.py        # Domain-specific routers
├── middleware/
│   ├── __init__.py
│   ├── cors_middleware.py        # CORS configuration
│   ├── auth_middleware.py        # Authentication hooks
│   └── rate_limit_middleware.py  # Rate limiting
├── models/
│   ├── __init__.py
│   ├── requests.py               # Client request models
│   ├── responses.py              # Client response models
│   └── errors.py                 # Error response models
├── implementations/
│   └── <protocol>_impl.py        # Protocol implementations
├── protocols.py                  # Service behavioral contracts
├── di.py                         # FastAPI + Dishka providers
├── config.py                     # Pydantic settings with FastAPI specifics
├── pyproject.toml
├── Dockerfile
└── tests/
```

### 2.2. FastAPI + Dishka Integration Pattern

**main.py Structure**:

```python
"""FastAPI application setup."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dishka.integrations.fastapi import setup_dishka

from .config import settings
from .startup_setup import create_di_container, initialize_middleware
from .routers.health_routes import health_router
from .routers.pipeline_routes import pipeline_router

app = FastAPI(
    title="HuleEdu API Gateway",
    description="Client-facing API for React frontend",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Initialize dependency injection
container = create_di_container()
setup_dishka(container, app)

# Configure CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Register routers
app.include_router(health_router)
app.include_router(pipeline_router, prefix="/v1")

# Initialize additional middleware
@app.on_event("startup")
async def startup():
    await initialize_middleware(app, settings)

@app.on_event("shutdown")
async def shutdown():
    await container.close()
```

### 2.3. Dependency Injection with FastAPI

**di.py Structure**:

```python
"""Dependency injection configuration for FastAPI service."""
from dishka import Provider, Scope, provide
from aiohttp import ClientSession
from huleedu_service_libs.kafka_client import KafkaBus
from prometheus_client import CollectorRegistry

from .config import Settings, settings
from .protocols import EventPublisherProtocol
from .implementations.kafka_publisher_impl import DefaultEventPublisher

class FastAPIServiceProvider(Provider):
    """Provider for FastAPI service dependencies."""
    
    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        return settings
    
    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        return CollectorRegistry()
    
    @provide(scope=Scope.APP)
    async def provide_kafka_bus(self, settings: Settings) -> KafkaBus:
        kafka_bus = KafkaBus(
            client_id=f"{settings.SERVICE_NAME}-producer",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
        )
        await kafka_bus.start()
        return kafka_bus
    
    @provide(scope=Scope.REQUEST)
    def provide_event_publisher(self, kafka_bus: KafkaBus) -> EventPublisherProtocol:
        return DefaultEventPublisher(kafka_bus)
```

### 2.4. Router Pattern (equivalent to Quart Blueprints)

**health_routes.py**:

```python
"""Health and documentation routes."""
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from dishka.integrations.fastapi import FromDishka
from prometheus_client import CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST

health_router = APIRouter(tags=["health"])

@health_router.get("/healthz")
async def health_check():
    return {"status": "ok", "message": "API Gateway is healthy"}

@health_router.get("/metrics")
async def metrics(registry: FromDishka[CollectorRegistry]):
    metrics_data = generate_latest(registry)
    return PlainTextResponse(metrics_data, media_type=CONTENT_TYPE_LATEST)
```

## 3. Service Library Compliance

### 3.1. Required Service Library Integration

**MUST** maintain compliance with existing service libraries:

- **Kafka Integration**: Use `huleedu_service_libs.kafka_client.KafkaBus`
- **Logging**: Use `huleedu_service_libs.logging_utils`
- **Metrics**: Use `prometheus_client` with service library patterns

### 3.2. Logging Integration

```python
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger

# Configure at startup
configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)
logger = create_service_logger("api_gateway.main")
```

### 3.3. Metrics Integration

```python
# startup_setup.py
from prometheus_client import Counter, Histogram, CollectorRegistry

def create_metrics(registry: CollectorRegistry) -> dict:
    """Create FastAPI-specific metrics."""
    return {
        "http_requests_total": Counter(
            "api_gateway_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"],
            registry=registry
        ),
        "http_request_duration_seconds": Histogram(
            "api_gateway_http_request_duration_seconds", 
            "HTTP request duration",
            ["method", "endpoint"],
            registry=registry
        )
    }
```

## 4. React Frontend Integration

### 4.1. CORS Configuration

**MUST** configure CORS middleware for React development and production:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # ["http://localhost:3000", "http://localhost:3001"]
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
```

### 4.2. Request/Response Models

**MUST** use Pydantic models optimized for React frontend consumption:

```python
from pydantic import BaseModel, Field

class PipelineRequestModel(BaseModel):
    """Client request model optimized for React forms."""
    batch_id: str = Field(min_length=1, max_length=255)
    requested_pipeline: str = Field(min_length=1, max_length=100)
    
    model_config = {
        "json_schema_extra": {
            "examples": [{"batch_id": "batch_123", "requested_pipeline": "ai_feedback"}]
        }
    }

class PipelineResponseModel(BaseModel):
    """Client response model optimized for React state management."""
    message: str
    batch_id: str
    correlation_id: str
    status: str = "accepted"
```

### 4.3. Error Response Format

**MUST** provide consistent error format for React error handling:

```python
from fastapi import HTTPException
from pydantic import BaseModel

class ErrorResponseModel(BaseModel):
    error: str
    detail: str | None = None
    correlation_id: str | None = None

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponseModel(
            error=exc.detail,
            correlation_id=getattr(request.state, "correlation_id", None)
        ).model_dump()
    )
```

## 5. Testing Patterns

### 5.1. FastAPI TestClient

```python
from fastapi.testclient import TestClient
from .main import app

def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

### 5.2. Dependency Override for Testing

```python
from dishka import make_container
from .di import FastAPIServiceProvider

def test_with_mock_dependencies():
    # Override dependencies for testing
    test_container = make_container(TestProvider())
    with app.container_context(test_container):
        client = TestClient(app)
        response = client.post("/v1/batches/test/pipelines", json={...})
        assert response.status_code == 202
```

## 6. Production Deployment

### 6.1. Docker Configuration

```dockerfile
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONPATH=/app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "services.api_gateway_service.main:app", "--host", "0.0.0.0", "--port", "4001"]
```

### 6.2. Health Check Integration

```yaml
# docker-compose.yml
healthcheck:
  test: ["CMD-SHELL", "curl -f http://localhost:4001/healthz || exit 1"]
  interval: 15s
  timeout: 5s
  retries: 3
  start_period: 20s
```

## 7. Compliance Checklist

**FastAPI Service Implementation**:

- [ ] Uses FastAPI with uvicorn for client-facing services only
- [ ] Maintains Dishka DI integration with service library compliance
- [ ] Implements CORS configuration for React frontend
- [ ] Uses service library patterns for Kafka, logging, and metrics
- [ ] Follows established protocol-based architecture
- [ ] Includes comprehensive OpenAPI documentation
- [ ] Implements proper error handling and rate limiting

**Service Library Integration**:

- [ ] Uses `huleedu_service_libs.kafka_client.KafkaBus`
- [ ] Uses `huleedu_service_libs.logging_utils`
- [ ] Maintains consistent metrics patterns
- [ ] Follows established DI provider patterns

---
**FastAPI is approved for client-facing services only. Internal services must use Quart.**
