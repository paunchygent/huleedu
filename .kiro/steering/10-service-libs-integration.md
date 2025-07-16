---
inclusion: always
---

# Service Libraries Integration Guide

## Mandatory Service Libraries Usage

### huleedu_service_libs Package Structure
The `services/libs/huleedu_service_libs/` package provides essential utilities that MUST be used:

```
huleedu_service_libs/
├── __init__.py                    # Main exports (KafkaBus, RedisClient, HuleEduApp, tracing)
├── logging_utils.py               # Structured logging with structlog
├── kafka_client.py                # Kafka producer abstractions (KafkaBus)
├── redis_client.py                # Redis operations with transactions
├── metrics_middleware.py          # Prometheus metrics middleware for Quart
├── quart_app.py                   # Type-safe HuleEduApp class
├── event_utils.py                 # Event processing utilities
├── idempotency_v2.py             # Advanced idempotency patterns
├── observability/                 # Distributed tracing utilities
├── error_handling/                # Structured error handling with factories
├── middleware/                    # Framework-specific middleware
├── database/                      # Database health checks and monitoring
└── resilience/                    # Circuit breaker patterns
```

## Logging Integration (MANDATORY)

### Correct Logging Usage
```python
# CORRECT - Use service library logging with structlog
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger

# Configure once at service startup
configure_service_logging(
    service_name="content-service",
    environment="production",  # or "development"
    log_level="INFO"
)

# Create logger instance
logger = create_service_logger(__name__)

# Standard logging with structured context (use keyword arguments, not extra={})
logger.info(
    "Processing started",
    essay_id=essay_id,
    batch_id=batch_id,
    correlation_id=correlation_id
)

# Error logging with context
logger.error(
    "Processing failed",
    essay_id=essay_id,
    error_type="ValidationError",
    correlation_id=correlation_id,
    exc_info=True
)
```

### FORBIDDEN Logging Patterns
```python
# FORBIDDEN - Direct logging import
import logging  # ❌ NEVER DO THIS
from logging import getLogger  # ❌ NEVER DO THIS

# FORBIDDEN - Standard library logging
logging.info("message")  # ❌ NEVER DO THIS
```

## Kafka Integration (MANDATORY)

### Correct Kafka Usage
```python
# CORRECT - Use service library KafkaBus (producer only)
from huleedu_service_libs import KafkaBus
from common_core.events.envelope import EventEnvelope

class EventPublisher:
    def __init__(self, kafka_bus: KafkaBus):
        self.kafka_bus = kafka_bus
    
    async def publish_event(self, event: EventEnvelope):
        await self.kafka_bus.publish(
            topic="essay-events",
            envelope=event
        )

# For Kafka consumers, use service-specific implementations
# KafkaBus is producer-only, consumers are service-specific
class EssayEventConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        # Use aiokafka directly for consumers (this is allowed for consumers)
    
    async def start_consuming(self):
        # Service-specific consumer implementation
        # Each service implements its own consumer pattern
        pass
```

### FORBIDDEN Kafka Patterns
```python
# FORBIDDEN - Direct aiokafka imports
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer  # ❌ NEVER DO THIS

# FORBIDDEN - Direct Kafka client usage
producer = AIOKafkaProducer()  # ❌ NEVER DO THIS
```

## Metrics Integration (MANDATORY)

### Standard Metrics Usage
```python
# CORRECT - Use service library metrics middleware
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware
from prometheus_client import Counter, Histogram, generate_latest

# In startup_setup.py
def setup_service(app: HuleEduApp) -> None:
    # Setup standard metrics middleware
    setup_standard_service_metrics_middleware(app, "content_service")
    
    # Create custom business metrics
    metrics = {
        "request_count": Counter("request_count", "Request count", ["method", "endpoint", "status_code"]),
        "request_duration": Histogram("request_duration", "Request duration", ["method", "endpoint"]),
        "essays_processed": Counter("essays_processed_total", "Essays processed", ["status"])
    }
    
    # Store metrics in app extensions
    app.extensions["metrics"] = metrics
    
    # Register metrics endpoint
    @app.route("/metrics")
    async def metrics_endpoint():
        return generate_latest()

# In service implementation - metrics are automatically collected by middleware
# Custom business metrics can be used directly
async def process_essay(essay_id: str):
    try:
        # Processing logic
        app.extensions["metrics"]["essays_processed"].labels(status="success").inc()
    except Exception as e:
        app.extensions["metrics"]["essays_processed"].labels(status="error").inc()
        raise
```

## Health Check Integration

### Standard Health Check Implementation
```python
from huleedu_service_libs.database import DatabaseHealthChecker
from quart import Blueprint, jsonify, current_app
from datetime import datetime

health_bp = Blueprint("health", __name__)

@health_bp.route("/healthz")
async def health_check():
    """Standard health check endpoint using service library utilities."""
    
    # Use the type-safe HuleEduApp to access guaranteed infrastructure
    engine = current_app.database_engine  # Guaranteed to exist
    
    # Create health checker with database engine
    health_checker = DatabaseHealthChecker(engine, "content_service")
    
    try:
        # Get comprehensive health summary
        health_summary = await health_checker.get_health_summary()
        
        # Add service-specific health checks
        health_summary["timestamp"] = datetime.utcnow().isoformat()
        health_summary["service_version"] = "1.0.0"
        
        status_code = 200 if health_summary["overall_status"] == "healthy" else 503
        return jsonify(health_summary), status_code
        
    except Exception as e:
        return jsonify({
            "overall_status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }), 503
```

## Error Handling Integration

### Structured Error Handling
```python
from huleedu_service_libs.error_handling import (
    HuleEduError,
    register_error_handlers,
    raise_resource_not_found,
    raise_processing_error
)

# Use existing error factories with correct signature
async def get_essay(essay_id: str, correlation_id: UUID):
    essay = await repository.get_by_id(essay_id)
    if not essay:
        raise_resource_not_found(
            service="content_service",
            operation="get_essay",
            resource_type="Essay",
            resource_id=essay_id,
            correlation_id=correlation_id
        )
    return essay

async def process_essay(essay_id: str, correlation_id: UUID):
    try:
        # Processing logic
        pass
    except Exception as e:
        raise_processing_error(
            service="content_service",
            operation="process_essay",
            message=f"Essay processing failed: {str(e)}",
            correlation_id=correlation_id,
            essay_id=essay_id,
            original_error=str(e)
        )

# In startup_setup.py
def setup_service(app: HuleEduApp) -> None:
    # Register error handlers for HuleEduError
    register_error_handlers(app)
```

## Circuit Breaker Integration

### External Service Protection
```python
from huleedu_service_libs.resilience import CircuitBreaker, circuit_breaker

class LLMServiceClient:
    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            timeout_seconds=30,
            recovery_timeout=60
        )
    
    async def generate_comparison(self, essay1: str, essay2: str) -> ComparisonResult:
        return await self.circuit_breaker.call(
            self._make_llm_request,
            essay1,
            essay2
        )
    
    # Alternative: Use decorator pattern
    @circuit_breaker(failure_threshold=5, timeout=30)
    async def _make_llm_request(self, essay1: str, essay2: str) -> ComparisonResult:
        # Actual LLM API call
        response = await self.http_client.post("/compare", json={
            "essay1": essay1,
            "essay2": essay2
        })
        return ComparisonResult.parse_obj(response.json())
```

## Dependency Injection Integration

### Service Library DI Registration
```python
# In di.py - Use Provider pattern (actual implementation)
from dishka import Provider, Scope, provide
from huleedu_service_libs import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger

class ServiceProvider(Provider):
    """DI provider for service dependencies."""
    
    @provide(scope=Scope.APP)
    def provide_kafka_bus(self, config: ServiceConfig) -> KafkaBus:
        """Provide KafkaBus instance."""
        return KafkaBus(
            client_id=f"{config.service_name}-producer",
            bootstrap_servers=config.kafka_bootstrap_servers
        )
    
    @provide(scope=Scope.APP)
    def provide_database_engine(self, config: ServiceConfig) -> AsyncEngine:
        """Provide database engine."""
        return create_async_engine(config.database_url)
    
    # Register service-specific components
    @provide(scope=Scope.REQUEST)
    def provide_essay_service(self, repository: EssayRepository) -> EssayService:
        return EssayService(repository)

# In startup_setup.py
from dishka import make_async_container

def create_di_container() -> AsyncContainer:
    """Creates and returns the DI AsyncContainer."""
    container = make_async_container(ServiceProvider())
    return container
```