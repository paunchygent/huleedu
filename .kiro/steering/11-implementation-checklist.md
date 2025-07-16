---
inclusion: always
---

# Implementation Checklist and Validation

## Pre-Implementation Validation

### Service Architecture Checklist
Before implementing any service code, verify:

- [ ] **Service Boundary Defined**: Clear bounded context and domain responsibility
- [ ] **Protocol Interfaces**: All abstractions defined in `protocols.py`
- [ ] **Service Library Dependencies**: `huleedu-service-libs` declared in `pyproject.toml`
- [ ] **Event Contracts**: Required events exist in `common_core` or planned
- [ ] **Database Schema**: Models and migrations planned if data persistence needed
- [ ] **Testing Strategy**: Unit, integration, and contract test approach defined

### Mandatory File Structure Validation
Every service MUST have this exact structure:

```
service_name/
├── pyproject.toml          # Service dependencies and metadata
├── app.py                  # HTTP service entry point (if HTTP service)
├── worker.py              # Kafka worker entry point (if worker service)
├── config.py              # Pydantic BaseSettings configuration
├── protocols.py           # Protocol interfaces (abstractions)
├── di.py                  # Dependency injection container setup
├── startup_setup.py       # Service initialization and middleware setup
├── api/                   # HTTP API blueprints (if HTTP service)
│   ├── __init__.py
│   └── service_api.py     # Main API blueprint
├── implementations/       # Concrete implementations of protocols
│   ├── __init__.py
│   ├── service_impl.py    # Main service implementation
│   └── repository_impl.py # Repository implementations
├── models/               # Database models (if applicable)
│   ├── __init__.py
│   └── entities.py       # SQLAlchemy models
├── migrations/           # Alembic migrations (if applicable)
└── tests/               # Comprehensive test suite
    ├── unit/
    ├── integration/
    ├── contract/
    └── fixtures/
```

## Service Library Integration Checklist

### ZERO TOLERANCE Compliance Items
These items have ZERO TOLERANCE for non-compliance:

- [ ] **NO Direct Logging**: No `import logging` or `from logging import` statements
- [ ] **Service Library Logging**: All logging via `huleedu_service_libs.logging_utils.create_service_logger`
- [ ] **NO Direct Kafka**: No `aiokafka.AIOKafkaProducer` or `aiokafka.AIOKafkaConsumer` imports for producers
- [ ] **Service Library Kafka**: All Kafka producer operations via `huleedu_service_libs.kafka_client.KafkaBus`
- [ ] **Metrics Integration**: `huleedu_service_libs.metrics_middleware` setup in `startup_setup.py`
- [ ] **Health Check Integration**: `huleedu_service_libs.database.DatabaseHealthChecker` implementation
- [ ] **Error Handling**: `huleedu_service_libs.error_handling` factories and middleware setup

### Service Library Import Validation
```python
# CORRECT imports - these are REQUIRED
from huleedu_service_libs.logging_utils import create_service_logger, configure_service_logging
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware
from huleedu_service_libs.database import DatabaseHealthChecker
from huleedu_service_libs.error_handling import HuleEduError, raise_resource_not_found

# FORBIDDEN imports - these will cause deployment failure
import logging  # ❌ FORBIDDEN
from logging import getLogger  # ❌ FORBIDDEN
from aiokafka import AIOKafkaProducer  # ❌ FORBIDDEN (for producers - use KafkaBus)
from aiokafka import AIOKafkaConsumer  # ❌ FORBIDDEN (for producers - consumers can use aiokafka directly)
```

## HTTP Service Implementation Checklist

### app.py Implementation
```python
# CORRECT app.py structure
from quart import Quart
from startup_setup import setup_service

app = Quart(__name__)
setup_service(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)
```

### startup_setup.py Implementation
```python
# MANDATORY startup_setup.py structure
from quart import Quart
from dishka.integrations.quart import setup_dishka
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware
from huleedu_service_libs.error_handling import register_error_handlers
from api.service_api import service_bp
from di import create_di_container

def setup_service(app: Quart) -> None:
    # Setup DI container
    container = create_di_container()
    setup_dishka(container, app)
    
    # Setup service library middleware
    setup_standard_service_metrics_middleware(app, "service_name")
    register_error_handlers(app)
    
    # Register API blueprints
    app.register_blueprint(service_bp)
    
    # Register health endpoint
    from api.health_api import health_bp
    app.register_blueprint(health_bp)
```

### API Blueprint Implementation
```python
# CORRECT API blueprint structure
from quart import Blueprint, request, jsonify
from dishka.integrations.quart import inject
from huleedu_service_libs.logging_utils import create_service_logger
from protocols import ServiceProtocol

logger = create_service_logger(__name__)
service_bp = Blueprint("service", __name__, url_prefix="/v1")

@service_bp.route("/endpoint", methods=["POST"])
@inject
async def handle_request(service: ServiceProtocol):
    try:
        data = await request.get_json()
        result = await service.process(data)
        
        logger.info(
            "Request processed successfully",
            endpoint="/endpoint",
            correlation_id=getattr(request, 'correlation_id', None)
        )
        
        return jsonify(result.dict())
    except Exception as e:
        logger.error(
            "Request processing failed",
            endpoint="/endpoint",
            error=str(e),
            exc_info=True
        )
        raise
```

## Worker Service Implementation Checklist

### worker.py Implementation
```python
# CORRECT worker.py structure
import asyncio
import signal
from huleedu_service_libs.logging_utils import create_service_logger
from di import create_di_container
from protocols import EventProcessorProtocol

logger = create_service_logger(__name__)

class WorkerService:
    def __init__(self, event_processor: EventProcessorProtocol):
        self.event_processor = event_processor
        self.running = True
    
    async def start(self):
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        logger.info("Starting worker service")
        
        try:
            await self.event_processor.start_processing()
        except Exception as e:
            logger.critical(f"Worker failed to start: {e}")
            raise
    
    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

async def main():
    container = create_di_container()
    async with container() as request_container:
        event_processor = await request_container.get(EventProcessorProtocol)
        worker = WorkerService(event_processor)
        await worker.start()

if __name__ == "__main__":
    asyncio.run(main())
```

## Testing Implementation Checklist

### Test Structure Validation
- [ ] **Unit Tests**: Fast, isolated tests in `tests/unit/`
- [ ] **Integration Tests**: External dependency tests in `tests/integration/`
- [ ] **Contract Tests**: Inter-service contract validation in `tests/contract/`
- [ ] **Test Fixtures**: Shared test data in `tests/fixtures/`
- [ ] **Protocol Testing**: Tests against protocol interfaces, not implementations
- [ ] **Async Test Support**: Proper async test configuration

### Test Implementation Example
```python
# CORRECT test structure
import pytest
from dishka import make_container
from protocols import ServiceProtocol

@pytest.fixture
async def service():
    container = make_test_container()
    async with container() as request_container:
        yield await request_container.get(ServiceProtocol)

@pytest.mark.asyncio
async def test_service_operation(service: ServiceProtocol):
    # Test against protocol, not implementation
    result = await service.process_data({"test": "data"})
    assert result is not None
```

## Deployment Readiness Checklist

### Pre-Deployment Validation
- [ ] **All Tests Pass**: `pdm run test-all` succeeds
- [ ] **Linting Passes**: `pdm run lint-all` succeeds
- [ ] **Type Checking Passes**: `pdm run typecheck-all` succeeds
- [ ] **Health Endpoint**: `/healthz` responds with dependency status
- [ ] **Metrics Endpoint**: `/metrics` provides Prometheus metrics
- [ ] **Graceful Shutdown**: Service handles SIGTERM/SIGINT properly
- [ ] **Docker Build**: Service builds successfully in container
- [ ] **Environment Variables**: All required config loaded from environment