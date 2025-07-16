---
inclusion: always
---

# Common Implementation Patterns

## HTTP Service Pattern (Quart-based)

### Standard HTTP Service Structure
```python
# app.py - Service entry point
from quart import Quart
from startup_setup import setup_service

app = Quart(__name__)
setup_service(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)
```

### Blueprint Pattern for APIs
```python
# api/content_api.py
from quart import Blueprint, request, jsonify
from dishka.integrations.quart import inject

content_bp = Blueprint("content", __name__, url_prefix="/v1/content")

@content_bp.route("/", methods=["POST"])
@inject
async def store_content(content_service: ContentServiceProtocol):
    # Implementation here
    pass
```

### Startup Setup Pattern
```python
# startup_setup.py
from dishka.integrations.quart import setup_dishka
from huleedu_service_libs.metrics import setup_metrics_middleware

def setup_service(app: Quart) -> None:
    container = make_container()
    setup_dishka(container, app)
    setup_metrics_middleware(app)
    # Register blueprints
    app.register_blueprint(content_bp)
```

## Kafka Worker Pattern

### Worker Service Structure
```python
# worker.py
import asyncio
import signal
from huleedu_service_libs.logging_utils import get_logger

logger = get_logger(__name__)

class WorkerService:
    def __init__(self, event_processor: EventProcessorProtocol):
        self.event_processor = event_processor
        self.running = True

    async def start(self):
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        try:
            await self.event_processor.start_processing()
        except Exception as e:
            logger.critical(f"Worker failed to start: {e}")
            raise

    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
```

## Configuration Pattern

### Pydantic Settings
```python
# config.py
from pydantic import BaseSettings, Field

class ServiceConfig(BaseSettings):
    service_name: str = "content-service"
    port: int = Field(default=8001, env="PORT")
    kafka_bootstrap_servers: str = Field(env="KAFKA_BOOTSTRAP_SERVERS")
    database_url: str = Field(env="DATABASE_URL")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

## Error Handling Patterns

### Structured Error Responses
```python
from huleedu_service_libs.error_handling import ServiceError, ErrorCode

class ContentNotFoundError(ServiceError):
    def __init__(self, content_id: str):
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=f"Content not found: {content_id}",
            details={"content_id": content_id}
        )
```

### Circuit Breaker Pattern
```python
from huleedu_service_libs.circuit_breaker import CircuitBreaker

@circuit_breaker(failure_threshold=5, timeout=30)
async def call_external_service():
    # External service call
    pass
```