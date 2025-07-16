---
inclusion: always
---

# Service Libraries Integration Guide

## Mandatory Service Libraries Usage

### huleedu_service_libs Package Structure
The `services/libs/huleedu_service_libs/` package provides essential utilities that MUST be used:

```
huleedu_service_libs/
├── __init__.py
├── logging_utils.py      # Centralized logging with correlation IDs
├── kafka_bus.py         # Kafka producer/consumer abstractions
├── metrics.py           # Prometheus metrics integration
├── health_check.py      # Health check utilities
├── error_handling.py    # Structured error handling
├── circuit_breaker.py   # Circuit breaker patterns
└── tracing.py          # Distributed tracing utilities
```

## Logging Integration (MANDATORY)

### Correct Logging Usage
```python
# CORRECT - Use service library logging
from huleedu_service_libs.logging_utils import get_logger

logger = get_logger(__name__)

# Standard logging with correlation ID
logger.info(
    "Processing started",
    extra={
        "essay_id": essay_id,
        "batch_id": batch_id,
        "correlation_id": correlation_id
    }
)

# Error logging with context
logger.error(
    "Processing failed",
    extra={
        "essay_id": essay_id,
        "error_type": "ValidationError",
        "correlation_id": correlation_id
    },
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
# CORRECT - Use service library KafkaBus
from huleedu_service_libs.kafka_bus import KafkaBus
from common_core.events import EventEnvelope

class EventPublisher:
    def __init__(self, kafka_bus: KafkaBus):
        self.kafka_bus = kafka_bus
    
    async def publish_event(self, event: EventEnvelope):
        await self.kafka_bus.publish(
            topic="essay-events",
            event=event
        )

# Service-specific Kafka consumer
class EssayEventConsumer:
    def __init__(self, kafka_bus: KafkaBus, event_processor: EventProcessorProtocol):
        self.kafka_bus = kafka_bus
        self.event_processor = event_processor
    
    async def start_consuming(self):
        await self.kafka_bus.consume(
            topics=["essay-events"],
            group_id="essay-lifecycle-service",
            handler=self._handle_event
        )
    
    async def _handle_event(self, event: EventEnvelope):
        await self.event_processor.process(event)
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
# CORRECT - Use service library metrics
from huleedu_service_libs.metrics import (
    setup_metrics_middleware,
    request_duration_histogram,
    request_count_counter,
    error_count_counter
)

# In startup_setup.py
def setup_service(app: Quart) -> None:
    # Setup metrics middleware
    setup_metrics_middleware(app)
    
    # Register metrics endpoint
    @app.route("/metrics")
    async def metrics():
        return generate_latest()

# In service implementation
@request_duration_histogram.time()
@request_count_counter.count()
async def process_essay(essay_id: str):
    try:
        # Processing logic
        pass
    except Exception as e:
        error_count_counter.inc(labels={"error_type": type(e).__name__})
        raise
```

## Health Check Integration

### Standard Health Check Implementation
```python
from huleedu_service_libs.health_check import HealthChecker, DependencyCheck

class ServiceHealthChecker(HealthChecker):
    def __init__(self, db_manager: DatabaseManager, kafka_bus: KafkaBus):
        self.db_manager = db_manager
        self.kafka_bus = kafka_bus
    
    async def check_dependencies(self) -> List[DependencyCheck]:
        checks = []
        
        # Database health
        try:
            await self.db_manager.health_check()
            checks.append(DependencyCheck("database", True, "Connected"))
        except Exception as e:
            checks.append(DependencyCheck("database", False, str(e)))
        
        # Kafka health
        try:
            await self.kafka_bus.health_check()
            checks.append(DependencyCheck("kafka", True, "Connected"))
        except Exception as e:
            checks.append(DependencyCheck("kafka", False, str(e)))
        
        return checks

# In API blueprint
@health_bp.route("/healthz")
async def health_check():
    health_checker = await get_health_checker()
    return await health_checker.get_health_response()
```

## Error Handling Integration

### Structured Error Handling
```python
from huleedu_service_libs.error_handling import (
    ServiceError,
    ErrorCode,
    error_handler_middleware
)

# Custom service errors
class EssayNotFoundError(ServiceError):
    def __init__(self, essay_id: str):
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=f"Essay not found: {essay_id}",
            details={"essay_id": essay_id}
        )

class EssayProcessingError(ServiceError):
    def __init__(self, essay_id: str, reason: str):
        super().__init__(
            code=ErrorCode.PROCESSING_FAILED,
            message=f"Essay processing failed: {reason}",
            details={"essay_id": essay_id, "reason": reason}
        )

# In startup_setup.py
def setup_service(app: Quart) -> None:
    # Setup error handling middleware
    error_handler_middleware(app)
```

## Circuit Breaker Integration

### External Service Protection
```python
from huleedu_service_libs.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

class LLMServiceClient:
    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client
        self.circuit_breaker = CircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold=5,
                timeout_seconds=30,
                recovery_timeout=60
            )
        )
    
    async def generate_comparison(self, essay1: str, essay2: str) -> ComparisonResult:
        return await self.circuit_breaker.call(
            self._make_llm_request,
            essay1,
            essay2
        )
    
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
# In di.py
from dishka import Container, make_container, Scope
from huleedu_service_libs.kafka_bus import KafkaBus
from huleedu_service_libs.logging_utils import get_logger

def make_service_container(config: ServiceConfig) -> Container:
    container = make_container()
    
    # Register service library components
    container.register(
        KafkaBus,
        factory=lambda: KafkaBus(config.kafka_bootstrap_servers),
        scope=Scope.SINGLETON
    )
    
    container.register(
        DatabaseManager,
        factory=lambda: DatabaseManager(config.database_url),
        scope=Scope.SINGLETON
    )
    
    # Register service-specific components
    container.register(EssayService, scope=Scope.REQUEST)
    container.register(EssayRepository, scope=Scope.REQUEST)
    
    return container
```