---
inclusion: manual
contextKey: production
---

# Production Readiness Standards

## Production Deployment Checklist

### Service Hardening Requirements
Every service MUST meet these production standards:

- [ ] **Graceful Shutdown**: Proper SIGTERM/SIGINT handling with resource cleanup
- [ ] **Health Checks**: Comprehensive `/healthz` endpoint with dependency validation
- [ ] **Metrics**: Prometheus metrics at `/metrics` with business and technical metrics
- [ ] **Error Handling**: Structured error responses with correlation IDs
- [ ] **Circuit Breakers**: External service protection with fallback mechanisms
- [ ] **Retry Logic**: Exponential backoff for transient failures
- [ ] **Connection Pooling**: Proper database and HTTP client connection management
- [ ] **Resource Limits**: Memory and CPU limits defined in Docker configuration

### Configuration Management
```python
# Production-ready configuration
from pydantic import BaseSettings, Field, validator
from typing import Optional

class ProductionConfig(BaseSettings):
    # Service identification
    service_name: str = Field(..., env="SERVICE_NAME")
    service_version: str = Field(..., env="SERVICE_VERSION")
    environment: str = Field(default="production", env="ENVIRONMENT")
    
    # Network configuration
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(..., env="PORT")
    
    # Database configuration
    database_url: str = Field(..., env="DATABASE_URL")
    database_pool_size: int = Field(default=10, env="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=20, env="DATABASE_MAX_OVERFLOW")
    
    # Kafka configuration
    kafka_bootstrap_servers: str = Field(..., env="KAFKA_BOOTSTRAP_SERVERS")
    kafka_group_id: str = Field(..., env="KAFKA_GROUP_ID")
    kafka_auto_offset_reset: str = Field(default="earliest", env="KAFKA_AUTO_OFFSET_RESET")
    
    # Redis configuration
    redis_url: str = Field(..., env="REDIS_URL")
    redis_pool_size: int = Field(default=10, env="REDIS_POOL_SIZE")
    
    # Observability configuration
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    metrics_enabled: bool = Field(default=True, env="METRICS_ENABLED")
    tracing_enabled: bool = Field(default=True, env="TRACING_ENABLED")
    
    # Security configuration
    cors_origins: list[str] = Field(default=[], env="CORS_ORIGINS")
    api_key_header: str = Field(default="X-API-Key", env="API_KEY_HEADER")
    
    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of: {valid_levels}')
        return v.upper()
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

### Graceful Shutdown Implementation
```python
import signal
import asyncio
from huleedu_service_libs.logging_utils import get_logger

logger = get_logger(__name__)

class GracefulShutdownHandler:
    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.cleanup_tasks = []
    
    def setup_signal_handlers(self):
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        logger.info(f"Received shutdown signal {signum}")
        self.shutdown_event.set()
    
    def register_cleanup(self, cleanup_func):
        """Register cleanup function to be called on shutdown"""
        self.cleanup_tasks.append(cleanup_func)
    
    async def wait_for_shutdown(self):
        await self.shutdown_event.wait()
        logger.info("Starting graceful shutdown...")
        
        # Execute cleanup tasks
        for cleanup_func in self.cleanup_tasks:
            try:
                await cleanup_func()
            except Exception as e:
                logger.error(f"Cleanup task failed: {e}")
        
        logger.info("Graceful shutdown complete")

# Usage in service
async def main():
    shutdown_handler = GracefulShutdownHandler()
    shutdown_handler.setup_signal_handlers()
    
    # Initialize service components
    kafka_bus = KafkaBus(config.kafka_bootstrap_servers)
    database = DatabaseManager(config.database_url)
    
    # Register cleanup functions
    shutdown_handler.register_cleanup(kafka_bus.close)
    shutdown_handler.register_cleanup(database.close)
    
    # Start service
    service_task = asyncio.create_task(start_service())
    shutdown_task = asyncio.create_task(shutdown_handler.wait_for_shutdown())
    
    # Wait for either service completion or shutdown signal
    done, pending = await asyncio.wait(
        [service_task, shutdown_task],
        return_when=asyncio.FIRST_COMPLETED
    )
    
    # Cancel pending tasks
    for task in pending:
        task.cancel()
```

### Production Error Handling
```python
from huleedu_service_libs.error_handling import ServiceError, ErrorCode
from huleedu_service_libs.logging_utils import get_logger

logger = get_logger(__name__)

class ProductionErrorHandler:
    @staticmethod
    async def handle_service_error(error: ServiceError, context: dict):
        """Handle service errors with proper logging and metrics"""
        logger.error(
            "Service error occurred",
            extra={
                "error_code": error.code,
                "error_message": error.message,
                "error_details": error.details,
                "context": context
            }
        )
        
        # Increment error metrics
        error_count_counter.inc(labels={
            "error_code": error.code,
            "service": context.get("service_name")
        })
    
    @staticmethod
    async def handle_unexpected_error(error: Exception, context: dict):
        """Handle unexpected errors with full context"""
        logger.critical(
            "Unexpected error occurred",
            extra={
                "error_type": type(error).__name__,
                "error_message": str(error),
                "context": context
            },
            exc_info=True
        )
        
        # Increment critical error metrics
        critical_error_counter.inc(labels={
            "error_type": type(error).__name__,
            "service": context.get("service_name")
        })
```

### Production Monitoring
```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Business metrics
essays_processed_total = Counter(
    'essays_processed_total',
    'Total number of essays processed',
    ['service', 'status', 'language']
)

processing_duration = Histogram(
    'essay_processing_duration_seconds',
    'Time spent processing essays',
    ['service', 'phase'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

active_batches = Gauge(
    'active_batches_count',
    'Number of currently active batches',
    ['service']
)

# System metrics
memory_usage = Gauge(
    'memory_usage_bytes',
    'Current memory usage in bytes',
    ['service']
)

database_connections = Gauge(
    'database_connections_active',
    'Number of active database connections',
    ['service', 'pool']
)

# Usage in service
class ProductionMetrics:
    def __init__(self, service_name: str):
        self.service_name = service_name
    
    def record_essay_processed(self, status: str, language: str):
        essays_processed_total.labels(
            service=self.service_name,
            status=status,
            language=language
        ).inc()
    
    def record_processing_time(self, phase: str, duration: float):
        processing_duration.labels(
            service=self.service_name,
            phase=phase
        ).observe(duration)
    
    def update_active_batches(self, count: int):
        active_batches.labels(service=self.service_name).set(count)
```

### Production Security
```python
from quart import request, abort
from functools import wraps
import hashlib
import hmac

class ProductionSecurity:
    def __init__(self, api_key: str, allowed_origins: list[str]):
        self.api_key = api_key
        self.allowed_origins = allowed_origins
    
    def require_api_key(self, f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            api_key = request.headers.get('X-API-Key')
            if not api_key or not self._verify_api_key(api_key):
                logger.warning(
                    "Unauthorized API access attempt",
                    extra={
                        "ip_address": request.remote_addr,
                        "user_agent": request.headers.get('User-Agent'),
                        "endpoint": request.endpoint
                    }
                )
                abort(401)
            return await f(*args, **kwargs)
        return decorated_function
    
    def _verify_api_key(self, provided_key: str) -> bool:
        """Secure API key verification using constant-time comparison"""
        return hmac.compare_digest(self.api_key, provided_key)
    
    async def validate_cors(self):
        """Validate CORS origins"""
        origin = request.headers.get('Origin')
        if origin and origin not in self.allowed_origins:
            logger.warning(
                "CORS violation detected",
                extra={
                    "origin": origin,
                    "allowed_origins": self.allowed_origins
                }
            )
            abort(403)
```

### Production Docker Configuration
```dockerfile
# Production Dockerfile
FROM python:3.11-slim

# Security: Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install dependencies
COPY pyproject.toml pdm.lock ./
RUN pip install pdm && pdm install --prod --no-dev

# Copy application code
COPY . .

# Set proper permissions
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/healthz || exit 1

# Expose port
EXPOSE ${PORT}

# Start application
CMD ["python", "app.py"]
```