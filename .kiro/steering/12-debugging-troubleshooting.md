---
inclusion: manual
contextKey: debugging
---

# Debugging and Troubleshooting Guide

## Common Issues and Solutions

### Service Library Import Issues

#### Problem: Import Errors for Service Libraries
```
ModuleNotFoundError: No module named 'huleedu_service_libs'
```

**Solution:**
1. Verify `huleedu-service-libs` is in `pyproject.toml` dependencies
2. Check that `services/libs` is properly installed in development environment
3. Run `pdm install` to ensure all dependencies are installed
4. Verify PYTHONPATH includes the service directory

#### Problem: Circular Import Errors
```
ImportError: cannot import name 'X' from partially initialized module
```

**Solution:**
1. Review import order in `__init__.py` files
2. Use forward references with `from __future__ import annotations`
3. Move imports inside functions if necessary
4. Restructure modules to eliminate circular dependencies

### Kafka Integration Issues

#### Problem: Kafka Connection Failures
```
KafkaConnectionError: Unable to connect to Kafka broker
```

**Solution:**
1. Verify Kafka is running: `pdm run dc-ps`
2. Check Kafka bootstrap servers configuration
3. Ensure topics are created: `pdm run kafka-setup-topics`
4. Verify network connectivity between services

#### Problem: Event Processing Failures
```
Event processing failed: Invalid event format
```

**Solution:**
1. Verify event contracts in `common_core` are up to date
2. Check event envelope structure matches `EventEnvelope`
3. Validate Pydantic model serialization/deserialization
4. Review correlation ID propagation

### Database Connection Issues

#### Problem: Database Connection Pool Exhaustion
```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 10 overflow 20 reached
```

**Solution:**
1. Review connection pool configuration in `DatabaseManager`
2. Ensure database sessions are properly closed
3. Use context managers for transaction handling
4. Check for connection leaks in repository implementations

#### Problem: Migration Failures
```
alembic.util.exc.CommandError: Can't locate revision identified by 'xyz'
```

**Solution:**
1. Verify migration files are in correct directory
2. Check Alembic configuration in `alembic.ini`
3. Ensure database schema is in sync with migrations
4. Review migration dependencies and ordering

### Dependency Injection Issues

#### Problem: Protocol Not Found in Container
```
dishka.exceptions.NoFactoryError: No factory found for protocol X
```

**Solution:**
1. Verify protocol is registered in `di.py`
2. Check implementation is properly bound to protocol
3. Ensure correct scope (SINGLETON, REQUEST) is used
4. Review container setup in `startup_setup.py`

#### Problem: Circular Dependencies in DI
```
dishka.exceptions.CircularDependencyError: Circular dependency detected
```

**Solution:**
1. Review dependency graph in `di.py`
2. Use factory functions to break circular dependencies
3. Consider splitting large services into smaller components
4. Use lazy initialization where appropriate

### HTTP Service Issues

#### Problem: Blueprint Registration Failures
```
AssertionError: A name collision occurred between blueprints
```

**Solution:**
1. Ensure unique blueprint names across service
2. Check URL prefix conflicts in blueprint registration
3. Review blueprint import order in `startup_setup.py`
4. Verify no duplicate route definitions

#### Problem: Health Check Failures
```
Health check endpoint returns 500 error
```

**Solution:**
1. Review health check implementation in `health_api.py`
2. Verify all dependencies are properly checked
3. Check database and Kafka connectivity
4. Review error handling in health check logic

### Performance Issues

#### Problem: High Memory Usage
```
Service consuming excessive memory
```

**Solution:**
1. Review database connection pooling configuration
2. Check for memory leaks in async operations
3. Monitor object lifecycle and garbage collection
4. Use memory profiling tools to identify bottlenecks

#### Problem: Slow Response Times
```
HTTP requests taking >2 seconds
```

**Solution:**
1. Review database query performance
2. Check external service call timeouts
3. Monitor Kafka consumer lag
4. Use distributed tracing to identify bottlenecks

## Debugging Tools and Techniques

### Logging for Debugging
```python
from huleedu_service_libs.logging_utils import get_logger

logger = get_logger(__name__)

# Debug level logging
logger.debug(
    "Processing step details",
    extra={
        "step": "validation",
        "data_size": len(data),
        "correlation_id": correlation_id
    }
)

# Error context logging
try:
    await process_data(data)
except Exception as e:
    logger.error(
        "Processing failed with context",
        extra={
            "data_keys": list(data.keys()),
            "error_type": type(e).__name__,
            "correlation_id": correlation_id
        },
        exc_info=True
    )
    raise
```

### Health Check Debugging
```python
# Enhanced health check for debugging
@health_bp.route("/healthz/detailed")
async def detailed_health_check():
    health_details = {
        "service": "healthy",
        "dependencies": {},
        "metrics": {},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Database health with details
    try:
        db_start = time.time()
        await database.execute("SELECT 1")
        db_time = time.time() - db_start
        health_details["dependencies"]["database"] = {
            "status": "healthy",
            "response_time_ms": round(db_time * 1000, 2)
        }
    except Exception as e:
        health_details["dependencies"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    return jsonify(health_details)
```

### Distributed Tracing for Debugging
```python
from huleedu_service_libs.tracing import get_correlation_id, create_span

async def debug_process_with_tracing(data):
    correlation_id = get_correlation_id()
    
    with create_span("data_validation") as span:
        span.set_attribute("data_size", len(data))
        await validate_data(data)
    
    with create_span("data_processing") as span:
        span.set_attribute("correlation_id", correlation_id)
        result = await process_data(data)
        span.set_attribute("result_size", len(result))
    
    return result
```

### Testing for Debugging
```python
# Debug test with detailed assertions
@pytest.mark.asyncio
async def test_service_with_debug_info(service: ServiceProtocol):
    test_data = {"key": "value"}
    
    # Capture logs for debugging
    with pytest.LoggingCapture() as log_capture:
        result = await service.process(test_data)
    
    # Assert with debug information
    assert result is not None, f"Service returned None for input: {test_data}"
    assert "processing_complete" in log_capture.messages, \
        f"Expected log message not found. Logs: {log_capture.messages}"
```