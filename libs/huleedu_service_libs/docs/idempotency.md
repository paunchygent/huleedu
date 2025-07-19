# Idempotency v2

Advanced idempotency decorator with service namespacing and configurable TTLs for message processing.

## Overview

Idempotency v2 provides advanced message processing protection with service isolation, event-type specific TTLs, and enhanced observability. It ensures that each unique event is processed exactly once, even in the face of retries or duplicate deliveries.

### Key Features

- **Service Isolation**: Each service maintains separate idempotency namespace
- **Event-Type Specific TTLs**: Optimized memory usage based on business requirements
- **Enhanced Observability**: Comprehensive structured logging for debugging
- **Robust Error Handling**: Fail-open behavior with proper cleanup
- **Backward Compatibility**: Drop-in replacement for existing decorator
- **Deterministic Event ID Generation**: Using proven hash algorithms
- **Atomic Redis Operations**: SET NX with configurable TTL
- **Automatic Lock Release**: On processing failures to allow retry

## API Reference

```python
class IdempotencyConfig:
    def __init__(
        self,
        service_name: str,
        event_type_ttls: Dict[str, int] | None = None,
        default_ttl: int = 86400,
        key_prefix: str = "huleedu:idempotency:v2",
        enable_debug_logging: bool = False,
    )
    
    def get_ttl_for_event_type(self, event_type: str) -> int
    def generate_redis_key(self, event_type: str, event_id: str, deterministic_hash: str) -> str

def idempotent_consumer_v2(
    redis_client: RedisClientProtocol,
    config: IdempotencyConfig,
) -> Callable

# Backward compatibility function
def idempotent_consumer(
    redis_client: RedisClientProtocol,
    ttl_seconds: int = 86400,
    service_name: str = "unknown-service",
) -> Callable
```

## Usage Examples

### V2 API (Recommended)

```python
from huleedu_service_libs.idempotency_v2 import idempotent_consumer_v2, IdempotencyConfig

# Configure idempotency with service-specific settings
config = IdempotencyConfig(
    service_name="essay-lifecycle-service",
    event_type_ttls={
        "huleedu.essay.spellcheck.requested.v1": 3600,  # 1 hour
        "huleedu.cj_assessment.completed.v1": 86400,    # 24 hours
        "huleedu.result_aggregator.batch.completed.v1": 259200,  # 72 hours
    },
    enable_debug_logging=True
)

@idempotent_consumer_v2(redis_client=redis_client, config=config)
async def handle_essay_submitted(msg: ConsumerRecord) -> None:
    envelope = EventEnvelope.model_validate_json(msg.value)
    
    # This will only execute once per unique event
    # TTL automatically determined by event type
    await process_essay(envelope.data)
    
    # If processing fails, the idempotency key is released
    # allowing natural retry on the next Kafka poll
```

### Backward Compatible API

```python
from huleedu_service_libs.idempotency_v2 import idempotent_consumer

@idempotent_consumer(
    redis_client=redis_client, 
    ttl_seconds=86400,
    service_name="my-service"
)
async def handle_message(msg: ConsumerRecord) -> None:
    # Existing code works unchanged
    envelope = EventEnvelope.model_validate_json(msg.value)
    await process_event(envelope.data)
```

## Service Namespacing

Redis keys are automatically namespaced by service for better isolation and debugging:

```
# Key format: {prefix}:{service}:{event_type}:{deterministic_hash}
huleedu:idempotency:v2:essay-lifecycle-service:huleedu_essay_submitted_v1:a1b2c3d4...
```

## Event-Type Specific TTLs

Pre-configured TTL mappings optimize Redis memory usage:

- **Quick Processing Events**: 1 hour (spellcheck, validation)
- **Batch Coordination**: 12 hours (workflow coordination)
- **Assessment Processing**: 24 hours (complex AI workflows)
- **Long-Running Processes**: 72 hours (batch operations, aggregations)

### TTL Configuration Example

```python
config = IdempotencyConfig(
    service_name="content-service",
    event_type_ttls={
        # Fast processing events
        "huleedu.content.validation.requested.v1": 1800,     # 30 minutes
        "huleedu.content.indexing.requested.v1": 3600,       # 1 hour
        
        # Standard processing
        "huleedu.content.created.v1": 86400,                 # 24 hours
        "huleedu.content.updated.v1": 86400,                 # 24 hours
        
        # Long-running processes
        "huleedu.content.batch.export.v1": 259200,           # 72 hours
        "huleedu.content.analytics.refresh.v1": 259200,      # 72 hours
    },
    default_ttl=43200,  # 12 hours default
    enable_debug_logging=True
)
```

## Enhanced Observability

Structured logging provides comprehensive debugging information:

```json
{
  "message": "DUPLICATE_EVENT_DETECTED: Event already processed, skipping",
  "service": "essay-lifecycle-service",
  "event_type": "huleedu.essay.submitted.v1",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "abc123",
  "source_service": "api-gateway",
  "deterministic_hash": "a1b2c3d4e5f6...",
  "redis_key": "huleedu:idempotency:v2:essay-lifecycle-service:huleedu_essay_submitted_v1:a1b2c3d4",
  "ttl_seconds": 86400,
  "action": "skipped_duplicate",
  "redis_duration_ms": 1.23,
  "total_duration_ms": 2.45
}
```

## Integration Patterns

### With Dependency Injection

```python
# In di.py
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig

@provide(scope=Scope.APP)
def provide_idempotency_config(settings: Settings) -> IdempotencyConfig:
    return IdempotencyConfig(
        service_name=settings.SERVICE_NAME,
        event_type_ttls=settings.IDEMPOTENCY_TTLS,
        enable_debug_logging=settings.ENVIRONMENT != "production"
    )

# In event processor
class EventProcessor:
    def __init__(
        self,
        redis_client: RedisClientProtocol,
        config: IdempotencyConfig
    ):
        self.redis_client = redis_client
        self.config = config
    
    @idempotent_consumer_v2(redis_client=self.redis_client, config=self.config)
    async def process_event(self, msg: ConsumerRecord) -> None:
        envelope = EventEnvelope.model_validate_json(msg.value)
        await self._handle_event(envelope)
```

### Multiple Event Types

```python
class MultiEventProcessor:
    def __init__(self, redis_client: RedisClientProtocol, config: IdempotencyConfig):
        self.redis_client = redis_client
        self.config = config
    
    @idempotent_consumer_v2(redis_client=self.redis_client, config=self.config)
    async def process_essay_events(self, msg: ConsumerRecord) -> None:
        envelope = EventEnvelope.model_validate_json(msg.value)
        
        if envelope.event_type == "huleedu.essay.submitted.v1":
            await self._handle_essay_submitted(envelope.data)
        elif envelope.event_type == "huleedu.essay.updated.v1":
            await self._handle_essay_updated(envelope.data)
        else:
            logger.warning(f"Unknown event type: {envelope.event_type}")
    
    @idempotent_consumer_v2(redis_client=self.redis_client, config=self.config)
    async def process_grading_events(self, msg: ConsumerRecord) -> None:
        envelope = EventEnvelope.model_validate_json(msg.value)
        # Different TTL rules apply based on event type
        await self._handle_grading_event(envelope)
```

## Error Handling and Recovery

### Automatic Lock Release

```python
@idempotent_consumer_v2(redis_client=redis_client, config=config)
async def process_with_error_handling(msg: ConsumerRecord) -> None:
    envelope = EventEnvelope.model_validate_json(msg.value)
    
    try:
        # Critical business logic
        await complex_processing(envelope.data)
        
        # This succeeds - idempotency key remains locked
        logger.info("Processing completed successfully")
        
    except CriticalBusinessError as e:
        # Processing failed - idempotency key is automatically released
        # This allows the event to be retried naturally
        logger.error(f"Processing failed: {e}")
        raise  # Re-raise to trigger Kafka retry
```

### Custom Error Handling

For advanced error handling patterns, you can manually manage idempotency keys:

```python
# Manual idempotency key management for custom retry logic
redis_key = config.generate_redis_key(event_type, event_id, deterministic_hash)
ttl = config.get_ttl_for_event_type(event_type)

is_first = await redis_client.set_if_not_exists(redis_key, "processing", ttl_seconds=ttl)
if not is_first:
    return  # Duplicate

try:
    await process_event(data)
    await redis_client.setex(redis_key, ttl, "completed")
except RetryableError:
    await redis_client.delete_key(redis_key)  # Release for retry
    raise
```

## Testing

### Testing Idempotency Behavior

```python
import pytest
from unittest.mock import AsyncMock
from huleedu_service_libs.idempotency_v2 import idempotent_consumer_v2, IdempotencyConfig

@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.set_if_not_exists.return_value = True  # First call
    return redis

@pytest.fixture
def idempotency_config():
    return IdempotencyConfig(
        service_name="test-service",
        enable_debug_logging=True
    )

async def test_idempotent_processing_first_time(mock_redis, idempotency_config):
    """Test that event is processed on first occurrence."""
    process_called = False
    
    @idempotent_consumer_v2(redis_client=mock_redis, config=idempotency_config)
    async def process_event(msg):
        nonlocal process_called
        process_called = True
    
    # Mock Kafka message
    msg = create_mock_kafka_message()
    
    await process_event(msg)
    
    assert process_called
    mock_redis.set_if_not_exists.assert_called_once()

async def test_idempotent_processing_duplicate(mock_redis, idempotency_config):
    """Test that duplicate event is skipped."""
    mock_redis.set_if_not_exists.return_value = False  # Duplicate
    
    process_called = False
    
    @idempotent_consumer_v2(redis_client=mock_redis, config=idempotency_config)
    async def process_event(msg):
        nonlocal process_called
        process_called = True
    
    msg = create_mock_kafka_message()
    await process_event(msg)
    
    assert not process_called  # Should be skipped
    mock_redis.set_if_not_exists.assert_called_once()
```

### Integration Testing

```python
async def test_idempotency_with_real_redis(redis_client):
    """Test idempotency with real Redis instance."""
    config = IdempotencyConfig(
        service_name="integration-test",
        default_ttl=60  # Short TTL for testing
    )
    
    call_count = 0
    
    @idempotent_consumer_v2(redis_client=redis_client, config=config)
    async def process_event(msg):
        nonlocal call_count
        call_count += 1
        return f"processed-{call_count}"
    
    # Create identical messages
    msg1 = create_test_kafka_message("test-event-123")
    msg2 = create_test_kafka_message("test-event-123")  # Same content
    
    # Process first message
    result1 = await process_event(msg1)
    assert call_count == 1
    
    # Process duplicate - should be skipped
    result2 = await process_event(msg2)
    assert call_count == 1  # No additional processing
```

## Best Practices

1. **Configure appropriate TTLs**: Match TTL to business requirements
2. **Enable debug logging**: Use in development for troubleshooting
3. **Service-specific configuration**: Use meaningful service names
4. **Handle processing failures**: Let idempotency decorator manage retries
5. **Monitor Redis memory**: TTLs should prevent unbounded growth
6. **Use v2 API**: Prefer the new API for new services
7. **Test idempotency**: Verify duplicate handling in tests
8. **Structured logging**: Include correlation IDs for tracing

## Migration from v1

```python
# Old v1 API (deprecated)
from huleedu_service_libs.idempotency import idempotent_consumer

@idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
async def handle_message(msg):
    # Process message
    pass

# New v2 API (recommended)
from huleedu_service_libs.idempotency_v2 import idempotent_consumer_v2, IdempotencyConfig

config = IdempotencyConfig(
    service_name="my-service",
    enable_debug_logging=True
)

@idempotent_consumer_v2(redis_client=redis_client, config=config)
async def handle_message(msg):
    # Same processing logic - no changes needed
    pass
```

## Anti-Patterns to Avoid

1. **Missing TTL configuration**: Always set appropriate TTLs
2. **Generic service names**: Use specific, meaningful service names
3. **Ignoring processing failures**: Handle errors appropriately
4. **Skipping testing**: Always test idempotency behavior
5. **Hardcoded TTLs**: Use configuration for TTL values
6. **Missing observability**: Enable debug logging in development
7. **Resource leaks**: Ensure Redis keys have TTLs
8. **Inconsistent event types**: Use consistent event type naming