# Kafka & Redis Infrastructure

Event publishing and distributed caching patterns for HuleEdu microservices.

## Overview

The Kafka and Redis clients provide reliable, async-first infrastructure for event-driven communication and distributed caching. Both clients feature lifecycle management, connection pooling, and graceful shutdown patterns.

## Kafka Client

**Module**: `kafka_client.py`  
**Protocol**: `KafkaPublisherProtocol`  
**Purpose**: Simplified async Kafka producer with lifecycle management

### Key Features

- Automatic EventEnvelope serialization
- Connection pooling and graceful shutdown
- Idempotent message delivery (`enable_idempotence=True`)
- Type-safe event publishing with generics

### API Reference

```python
class KafkaBus:
    def __init__(self, *, client_id: str, bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS)
    async def start(self) -> None
    async def stop(self) -> None
    async def publish(
        self,
        topic: str,
        envelope: EventEnvelope[T_EventPayload],
        key: str | None = None,
    ) -> None
```

### Usage Example

```python
from huleedu_service_libs import KafkaBus
from common_core.events.envelope import EventEnvelope

# Initialize with explicit client ID
kafka_bus = KafkaBus(client_id="content-service-producer")

# Lifecycle management
await kafka_bus.start()
try:
    # Publish events
    envelope = EventEnvelope(
        event_type="CONTENT_CREATED",
        source_service="content_service",
        data=ContentCreatedEvent(...)
    )
    await kafka_bus.publish("content-events", envelope)
finally:
    await kafka_bus.stop()
```

### Configuration

- `KAFKA_BOOTSTRAP_SERVERS`: Default `"kafka:9092"`
- Acks: `"all"` (wait for all replicas)
- Idempotence: Enabled by default

## Redis Client

**Module**: `redis_client.py`  
**Protocol**: `RedisClientProtocol`, `AtomicRedisClientProtocol`  
**Purpose**: Redis operations with transaction support and pub/sub delegation

### Key Features

- Atomic operations for idempotency (`SET NX`)
- WATCH/MULTI/EXEC transaction support
- Pattern scanning for bulk operations
- Integrated pub/sub via `RedisPubSub`
- Explicit lifecycle management

### API Reference

```python
class RedisClient:
    def __init__(self, *, client_id: str, redis_url: str = REDIS_URL)
    async def start(self) -> None
    async def stop(self) -> None
    
    # Basic operations
    async def set_if_not_exists(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool
    async def get(self, key: str) -> str | None
    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool
    async def delete_key(self, key: str) -> int
    async def ping(self) -> bool
    
    # Transactions
    async def watch(self, *keys: str) -> bool
    async def multi(self) -> bool
    async def exec(self) -> list[Any] | None
    async def unwatch(self) -> bool
    
    # Pattern operations
    async def scan_pattern(self, pattern: str) -> list[str]
    
    # Pub/Sub (delegated)
    async def publish(self, channel: str, message: str) -> int
    async def subscribe(self, channel: str) -> AsyncGenerator
    def get_user_channel(self, user_id: str) -> str
    async def publish_user_notification(self, user_id: str, event_type: str, data: dict) -> int
```

### Usage Examples

#### Idempotency Pattern

```python
from huleedu_service_libs import RedisClient

redis_client = RedisClient(client_id="cj-assessment-redis")
await redis_client.start()

# Check for duplicate processing
key = f"processed:{event_id}"
is_first = await redis_client.set_if_not_exists(key, "1", ttl_seconds=86400)
if not is_first:
    logger.warning(f"Duplicate event {event_id}")
    return
```

#### Transaction Pattern

```python
# Atomic counter increment
await redis_client.watch("counter")
current = await redis_client.get("counter")
await redis_client.multi()
await redis_client.setex("counter", 3600, str(int(current or 0) + 1))
result = await redis_client.exec()
if result is None:  # Transaction failed
    logger.warning("Counter update conflict")
```

#### Pub/Sub Pattern

```python
# Publish to user channel
await redis_client.publish_user_notification(
    user_id="user123",
    event_type="essay_graded",
    data={"essay_id": "essay456", "score": 85}
)

# Subscribe to channel
async with redis_client.subscribe("ws:user123") as pubsub:
    async for msg in pubsub.listen():
        if msg["type"] == "message":
            data = json.loads(msg["data"])
            # Process notification
```

### Configuration

- `REDIS_URL`: Default `"redis://redis:6379"`
- Connection timeout: 5 seconds
- Socket timeout: 5 seconds

## Redis Pub/Sub

**Module**: `redis_pubsub.py`  
**Purpose**: Real-time messaging and WebSocket notification patterns

### API Reference

```python
class RedisPubSub:
    def __init__(self, redis_client: RedisClientProtocol)
    async def start(self) -> None
    async def stop(self) -> None
    
    async def publish(self, channel: str, message: str) -> int
    async def subscribe(self, channel: str) -> AsyncGenerator[dict, None]
    def get_user_channel(self, user_id: str) -> str
    async def publish_user_notification(self, user_id: str, event_type: str, data: dict) -> int
```

### Usage Example

```python
from huleedu_service_libs.redis_pubsub import RedisPubSub

pubsub = RedisPubSub(redis_client)
await pubsub.start()

try:
    # Subscribe to user notifications
    user_channel = pubsub.get_user_channel("user123")
    async for message in pubsub.subscribe(user_channel):
        if message["type"] == "message":
            notification = json.loads(message["data"])
            await websocket.send(json.dumps(notification))
finally:
    await pubsub.stop()
```

## Event Utilities

**Module**: `event_utils.py`  
**Purpose**: Event processing helpers for idempotency and user notifications

### API Reference

```python
def extract_user_id_from_event_data(event_data: Any) -> str | None
def extract_correlation_id_as_string(correlation_id: Any) -> str | None
def generate_deterministic_event_id(msg_value: bytes) -> str
def extract_correlation_id_from_event(msg_value: bytes) -> str | None
```

### Usage Example

```python
from huleedu_service_libs.event_utils import (
    generate_deterministic_event_id,
    extract_user_id_from_event_data
)

# Generate deterministic ID for idempotency
event_id = generate_deterministic_event_id(kafka_message.value)
idempotency_key = f"processed:{event_id}"

# Extract user for notifications
user_id = extract_user_id_from_event_data(envelope.data)
if user_id:
    await redis_client.publish_user_notification(
        user_id=user_id,
        event_type="essay_processed",
        data={"essay_id": envelope.data.essay_id}
    )
```

## Dependency Injection Patterns

### Basic DI Setup

```python
# In di.py
from dishka import Provider, Scope, provide
from huleedu_service_libs import KafkaBus, RedisClient
from huleedu_service_libs.protocols import KafkaPublisherProtocol, RedisClientProtocol

class ServiceProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_kafka_bus(self, settings: Settings) -> KafkaPublisherProtocol:
        kafka_bus = KafkaBus(client_id=f"{settings.SERVICE_NAME}-producer")
        await kafka_bus.start()
        return kafka_bus
    
    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> RedisClientProtocol:
        redis_client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis",
            redis_url=settings.REDIS_URL
        )
        await redis_client.start()
        return redis_client
```

### Using in Services

```python
# In service implementations
class ContentServiceImpl:
    def __init__(
        self,
        kafka_bus: KafkaPublisherProtocol,
        redis_client: RedisClientProtocol
    ):
        self.kafka_bus = kafka_bus
        self.redis_client = redis_client
    
    async def create_content(self, data: dict) -> Content:
        # Check idempotency
        key = f"content_creation:{data['user_id']}:{data['title']}"
        is_first = await self.redis_client.set_if_not_exists(key, "1", ttl_seconds=3600)
        if not is_first:
            raise DuplicateOperationError()
        
        # Create content
        content = Content(...)
        
        # Publish event
        envelope = EventEnvelope(
            event_type="CONTENT_CREATED",
            source_service="content_service",
            data=ContentCreatedEvent(content_id=content.id)
        )
        await self.kafka_bus.publish("content-events", envelope)
        
        return content
```

## Testing Patterns

### Protocol-Based Mocking

```python
from unittest.mock import AsyncMock
from huleedu_service_libs.protocols import RedisClientProtocol, KafkaPublisherProtocol

# Mock Redis client
mock_redis = AsyncMock(spec=RedisClientProtocol)
mock_redis.set_if_not_exists.return_value = True
mock_redis.get.return_value = "cached_value"

# Mock Kafka publisher
mock_kafka = AsyncMock(spec=KafkaPublisherProtocol)
mock_kafka.publish.return_value = None

# Inject mocks
service = ContentServiceImpl(kafka_bus=mock_kafka, redis_client=mock_redis)
```

### Integration Testing

```python
import pytest
from testcontainers.redis import RedisContainer
from testcontainers.kafka import KafkaContainer

@pytest.fixture
async def redis_client():
    with RedisContainer() as redis:
        client = RedisClient(
            client_id="test-redis",
            redis_url=redis.get_connection_url()
        )
        await client.start()
        yield client
        await client.stop()

@pytest.fixture
async def kafka_bus():
    with KafkaContainer() as kafka:
        bus = KafkaBus(
            client_id="test-kafka",
            bootstrap_servers=kafka.get_bootstrap_server()
        )
        await bus.start()
        yield bus
        await bus.stop()
```

## Best Practices

1. **Always use lifecycle management**: Call `start()` and `stop()` on clients
2. **Use protocols for dependency injection**: Depend on protocols, not concrete classes
3. **Proper client IDs**: Use descriptive client IDs for debugging and monitoring
4. **Graceful shutdown**: Always stop clients in finally blocks or cleanup handlers
5. **Idempotency keys**: Use Redis SET NX for duplicate protection
6. **Connection pooling**: Reuse client instances across requests
7. **Error handling**: Handle Redis/Kafka unavailability gracefully
8. **Structured logging**: Log client operations with correlation IDs

## Anti-Patterns to Avoid

1. **Direct client instantiation in handlers**: Use dependency injection
2. **Forgetting lifecycle management**: Always start/stop clients properly
3. **Synchronous Redis operations**: All operations are async
4. **Blocking pub/sub**: Use async generators for message processing
5. **Missing error handling**: Always handle connection failures
6. **Hardcoded configuration**: Use environment variables
7. **Resource leaks**: Ensure proper cleanup in all code paths
