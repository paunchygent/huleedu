# Queue Redis Architecture and Usage Documentation

## Overview

The Queue Redis architecture in HuleEdu provides specialized Redis operations for queue-based implementations, separate from general-purpose Redis operations. This architecture enables high-performance queue management with Redis sorted sets for priority ordering and hashes for structured data storage.

## Architecture Overview

### Design Principles

1. **Separation of Concerns**: Queue-specific Redis operations are isolated from general Redis operations through dedicated protocols
2. **Performance-First Design**: Built around Redis pipelines and batch operations for optimal performance
3. **Protocol-Based Architecture**: Uses typing.Protocol for interface contracts, enabling easy testing and dependency injection
4. **Resilience**: Built-in connection management, error handling, and lifecycle management

### Key Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    Queue Redis Architecture                      │
├─────────────────────────────────────────────────────────────────┤
│  QueueRedisClientProtocol                                       │
│  ├── Lifecycle Management (start/stop/ping)                     │
│  ├── Sorted Set Operations (zadd/zrange/zrem/zcard)            │
│  ├── Hash Operations (hset/hget/hdel/hmget/hgetall/hkeys)       │
│  ├── Key Operations (exists/delete/setex)                      │
│  └── Pipeline Operations (pipeline() -> QueueRedisPipelineProtocol) │
├─────────────────────────────────────────────────────────────────┤
│  QueueRedisPipelineProtocol                                     │
│  ├── Batch Operations (zadd/zrem/hset/hdel/delete/setex)        │
│  └── Atomic Execution (execute())                              │
├─────────────────────────────────────────────────────────────────┤
│  QueueRedisClient (Implementation)                              │
│  ├── Connection Management                                      │
│  ├── Error Handling & Logging                                  │
│  ├── Protocol Implementation                                   │
│  └── Pipeline Factory                                          │
└─────────────────────────────────────────────────────────────────┘
```

## Protocol Interface Documentation

### QueueRedisClientProtocol

The main protocol interface for queue-specific Redis operations.

#### Lifecycle Management

```python
async def start(self) -> None:
    """Initialize Redis connection with health verification."""
    
async def stop(self) -> None:
    """Clean shutdown of Redis connection."""
    
async def ping(self) -> bool:
    """Health check method to verify Redis connectivity."""
```

#### Sorted Set Operations (Priority Queue Management)

```python
async def zadd(self, key: str, mapping: dict[str, float]) -> int:
    """Add members to sorted set with scores for priority ordering."""
    
async def zrange(self, key: str, start: int, end: int, withscores: bool = False) -> List[str] | List[tuple[str, float]]:
    """Get range of members from sorted set by rank (priority order)."""
    
async def zrem(self, key: str, *members: str) -> int:
    """Remove members from sorted set."""
    
async def zcard(self, key: str) -> int:
    """Get cardinality (count) of sorted set."""
```

#### Hash Operations (Structured Data Storage)

```python
async def hset(self, key: str, field: str, value: str) -> int:
    """Set field in hash (typically JSON-serialized queue data)."""
    
async def hget(self, key: str, field: str) -> Optional[str]:
    """Get field from hash."""
    
async def hmget(self, key: str, *fields: str) -> List[Optional[str]]:
    """Get multiple fields from hash in single operation."""
    
async def hgetall(self, key: str) -> dict[str, str]:
    """Get all fields and values from hash."""
```

#### Pipeline Operations

```python
def pipeline(self) -> QueueRedisPipelineProtocol:
    """Create pipeline for batch operations."""
```

### QueueRedisPipelineProtocol

Protocol for batched Redis operations with atomic execution.

```python
def zadd(self, key: str, mapping: dict[str, float]) -> QueueRedisPipelineProtocol:
    """Queue zadd operation in pipeline."""
    
def hset(self, key: str, field: str, value: str) -> QueueRedisPipelineProtocol:
    """Queue hset operation in pipeline."""
    
async def execute(self) -> List[Any]:
    """Execute all queued operations atomically."""
```

## Implementation Details

### QueueRedisClient

The concrete implementation of `QueueRedisClientProtocol`.

#### Connection Management

```python
class QueueRedisClient(QueueRedisClientProtocol):
    def __init__(self, *, client_id: str, redis_url: str = REDIS_URL):
        self.client_id = client_id
        self.client = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        self._started = False
```

#### Performance Characteristics

- **Connection Pooling**: Uses aioredis connection pooling for efficient connection management
- **Decode Responses**: Automatically decodes Redis responses to strings for easier handling
- **Timeouts**: Configured with 5-second socket connect and operation timeouts
- **Lifecycle Management**: Explicit start/stop methods for proper resource management

#### Error Handling

```python
async def zadd(self, key: str, mapping: dict[str, float]) -> int:
    """Add members to sorted set with scores."""
    self._ensure_started()
    try:
        result = await self.client.zadd(key, mapping)
        logger.debug(f"Queue Redis ZADD by '{self.client_id}': key='{key}' added={result}")
        return int(result)
    except Exception as e:
        logger.error(f"Error in Queue Redis ZADD operation by '{self.client_id}' for key '{key}': {e}", exc_info=True)
        raise
```

#### Pipeline Implementation

```python
class QueueRedisPipeline:
    def __init__(self, pipeline: aioredis.Pipeline, client_id: str):
        self._pipeline = pipeline
        self._client_id = client_id
        
    async def execute(self) -> List[Any]:
        """Execute all queued operations atomically."""
        try:
            result = await self._pipeline.execute()
            logger.debug(f"Queue Redis pipeline executed by '{self._client_id}': {len(result)} operations")
            return result
        except Exception as e:
            logger.error(f"Queue Redis pipeline execution failed for '{self._client_id}': {e}", exc_info=True)
            raise
```

## Usage Patterns

### Integration with Dishka DI Container

```python
class LLMProviderServiceProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_queue_redis_client(self, settings: Settings) -> QueueRedisClientProtocol:
        """Provide specialized Redis client for queue operations."""
        queue_redis_client = QueueRedisClient(
            client_id=f"{settings.SERVICE_NAME}-queue-redis",
            redis_url=settings.REDIS_URL,
        )
        await queue_redis_client.start()
        return queue_redis_client
```

### Real-World Usage Example: RedisQueueRepositoryImpl

The LLM Provider Service demonstrates practical usage of the Queue Redis architecture:

#### Queue Data Structure

```python
class RedisQueueRepositoryImpl(QueueRepositoryProtocol):
    def __init__(self, redis_client: QueueRedisClientProtocol, settings: Settings):
        self.redis = redis_client
        self.prefix = f"{settings.SERVICE_NAME}:queue"
        
        # Key patterns for queue management
        self.queue_key = f"{self.prefix}:requests"    # Sorted set for priority ordering
        self.data_key = f"{self.prefix}:data"         # Hash for request data storage
        self.stats_key = f"{self.prefix}:stats"       # Hash for statistics
```

#### Priority Queue Implementation

```python
async def add(self, request: QueuedRequest) -> bool:
    """Add request to Redis queue with priority ordering."""
    # Calculate score for sorted set (higher priority = lower score)
    timestamp = request.queued_at.timestamp()
    score = -request.priority + (timestamp / 1e10)  # Negative for descending priority
    
    # Use pipeline for atomic operations
    pipe = self.redis.pipeline()
    pipe.zadd(self.queue_key, {str(request.queue_id): score})
    pipe.hset(self.data_key, str(request.queue_id), request.model_dump_json())
    pipe.setex(f"{self.data_key}:{request.queue_id}", int(request.ttl.total_seconds()), "1")
    
    results = await pipe.execute()
    return all(results)
```

#### Batch Operations for Performance

```python
async def get_all_queued(self) -> List[QueuedRequest]:
    """Get all QUEUED status requests using optimized batch operations."""
    # Get all queue IDs from sorted set
    queue_ids = await self.redis.zrange(self.queue_key, 0, -1)
    
    if not queue_ids:
        return []
    
    # Batch get all data using hmget (single Redis call instead of N calls)
    request_jsons = await self.redis.hmget(self.data_key, *queue_ids)
    
    requests = []
    for queue_id_str, request_json in zip(queue_ids, request_jsons):
        if request_json:
            try:
                request = QueuedRequest.model_validate_json(request_json)
                if request.status == QueueStatus.QUEUED and not request.is_expired():
                    requests.append(request)
            except Exception as e:
                logger.warning(f"Failed to parse request {queue_id_str}: {e}")
    
    return requests
```

#### Batch Cleanup Operations

```python
async def _batch_cleanup_invalid_requests(self, orphaned_ids: List[str], expired_ids: List[str]) -> None:
    """Batch cleanup orphaned and expired requests using direct operations."""
    if not orphaned_ids and not expired_ids:
        return
    
    # Use pipeline for proper batch operations
    pipe = self.redis.pipeline()
    
    # Clean up orphaned entries (missing data)
    for queue_id_str in orphaned_ids:
        pipe.zrem(self.queue_key, queue_id_str)
    
    # Clean up expired entries (full cleanup)
    for queue_id_str in expired_ids:
        pipe.zrem(self.queue_key, queue_id_str)
        pipe.hdel(self.data_key, queue_id_str)
        pipe.delete(f"{self.data_key}:{queue_id_str}")
    
    await pipe.execute()
```

## Performance Characteristics

### Benchmarking Results

Based on performance tests with real Redis infrastructure:

#### Individual Operations
- **Average Redis Operation Time**: 0.3ms (sub-millisecond performance)
- **Pipeline Operations**: Under 100ms for 10 operations
- **Batch Retrievals**: Under 200ms for 10 queue retrievals
- **Memory Usage Calculations**: Under 100ms per operation

#### Batch Operations
- **Batch Addition**: Under 150ms per request for 20 concurrent requests
- **Concurrent Operations**: 25 concurrent operations in under 5 seconds
- **Pipeline Throughput**: 25+ operations per second under load

#### Resilience
- **Error Recovery**: Under 500ms average recovery time
- **Success Rate**: 90%+ success rate under stress conditions
- **Connection Stability**: Automatic reconnection and health checking

### Scaling Guidance

#### Connection Management
- Use single `QueueRedisClient` instance per service
- Leverage Redis connection pooling (handled by aioredis)
- Implement proper lifecycle management with start/stop methods

#### Performance Optimization
1. **Use Pipelines**: Always use pipeline operations for batch operations
2. **Batch Operations**: Prefer `hmget` over multiple `hget` calls
3. **Key Design**: Use consistent key patterns for efficient operations
4. **Connection Reuse**: Maintain long-lived connections rather than per-operation connections

#### Memory Management
- Implement TTL on queue data to prevent memory leaks
- Use expiration markers for efficient cleanup
- Monitor memory usage with `get_memory_usage()` method

## Best Practices

### 1. Protocol Separation

```python
# Correct: Use QueueRedisClientProtocol for queue operations
class QueueRepository:
    def __init__(self, redis_client: QueueRedisClientProtocol):
        self.redis = redis_client

# Incorrect: Using general RedisClientProtocol for queue operations
class QueueRepository:
    def __init__(self, redis_client: RedisClientProtocol):  # Wrong protocol
        self.redis = redis_client
```

### 2. Pipeline Usage

```python
# Correct: Use pipeline for batch operations
async def batch_update(self, updates: List[tuple[str, str]]) -> None:
    pipe = self.redis.pipeline()
    for key, value in updates:
        pipe.hset(self.data_key, key, value)
    await pipe.execute()

# Incorrect: Multiple individual operations
async def batch_update(self, updates: List[tuple[str, str]]) -> None:
    for key, value in updates:
        await self.redis.hset(self.data_key, key, value)  # Multiple round trips
```

### 3. Error Handling

```python
# Correct: Proper error handling with context
async def get_request(self, queue_id: str) -> Optional[QueuedRequest]:
    try:
        request_json = await self.redis.hget(self.data_key, queue_id)
        if not request_json:
            return None
        return QueuedRequest.model_validate_json(request_json)
    except Exception as e:
        logger.error(f"Failed to get request {queue_id}: {e}")
        return None

# Incorrect: No error handling
async def get_request(self, queue_id: str) -> Optional[QueuedRequest]:
    request_json = await self.redis.hget(self.data_key, queue_id)
    return QueuedRequest.model_validate_json(request_json)  # Can raise exceptions
```

### 4. Key Management

```python
# Correct: Consistent key patterns
class QueueRepository:
    def __init__(self, redis_client: QueueRedisClientProtocol, settings: Settings):
        self.redis = redis_client
        self.prefix = f"{settings.SERVICE_NAME}:queue"
        self.queue_key = f"{self.prefix}:requests"
        self.data_key = f"{self.prefix}:data"
        
# Incorrect: Inconsistent key patterns
class QueueRepository:
    def __init__(self, redis_client: QueueRedisClientProtocol):
        self.redis = redis_client
        # Keys scattered throughout methods, no consistent pattern
```

## Testing Patterns

### Protocol-Based Testing

```python
@pytest.fixture
async def mock_queue_redis_client() -> AsyncMock:
    """Create mock queue Redis client for testing."""
    mock = AsyncMock(spec=QueueRedisClientProtocol)
    mock.ping.return_value = True
    mock.zadd.return_value = 1
    mock.hset.return_value = 1
    return mock

async def test_queue_operations(mock_queue_redis_client: AsyncMock):
    queue_repo = RedisQueueRepositoryImpl(mock_queue_redis_client, settings)
    
    # Test with protocol mock
    result = await queue_repo.add(test_request)
    
    # Verify protocol interactions
    mock_queue_redis_client.pipeline.assert_called_once()
```

### Integration Testing

```python
@pytest.fixture
async def redis_queue_client(redis_container: RedisContainer) -> QueueRedisClientProtocol:
    """Provide real Redis client for integration testing."""
    redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"
    client = QueueRedisClient(client_id="test-client", redis_url=redis_url)
    await client.start()
    yield client
    await client.stop()
```

## Operational Considerations

### Monitoring

Monitor these key metrics:

1. **Connection Health**: Use `ping()` method for health checks
2. **Operation Latency**: Track pipeline execution times
3. **Error Rates**: Monitor Redis connection and operation errors
4. **Memory Usage**: Track queue memory consumption with `get_memory_usage()`

### Deployment

```yaml
# docker-compose.yml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
```

### Configuration

```python
# Environment variables
REDIS_URL=redis://redis:6379/0  # Default Redis URL
SERVICE_NAME=llm_provider_service  # Used for key prefixes and client IDs
```

## Migration Guide

### From General Redis to Queue Redis

1. **Update Protocol Dependencies**:
   ```python
   # Old
   from huleedu_service_libs.protocols import RedisClientProtocol
   
   # New
   from huleedu_service_libs.queue_protocols import QueueRedisClientProtocol
   ```

2. **Update DI Configuration**:
   ```python
   # Old
   @provide(scope=Scope.APP)
   async def provide_redis_client(self, settings: Settings) -> RedisClientProtocol:
       return RedisClient(client_id="service-redis", redis_url=settings.REDIS_URL)
   
   # New
   @provide(scope=Scope.APP)
   async def provide_queue_redis_client(self, settings: Settings) -> QueueRedisClientProtocol:
       client = QueueRedisClient(client_id=f"{settings.SERVICE_NAME}-queue-redis", redis_url=settings.REDIS_URL)
       await client.start()
       return client
   ```

3. **Update Repository Implementations**:
   ```python
   # Old
   class QueueRepository:
       def __init__(self, redis_client: RedisClientProtocol):
           self.redis = redis_client
   
   # New
   class QueueRepository:
       def __init__(self, redis_client: QueueRedisClientProtocol):
           self.redis = redis_client
   ```

## Conclusion

The Queue Redis architecture provides a specialized, high-performance solution for queue management in HuleEdu's microservice architecture. By separating queue-specific operations from general Redis operations, it offers:

- **Better Performance**: Optimized for queue operations with pipelines and batch processing
- **Clear Separation**: Dedicated protocols prevent mixing of concerns
- **Easy Testing**: Protocol-based design enables comprehensive testing
- **Resilience**: Built-in error handling and connection management
- **Scalability**: Designed for high-throughput queue operations

This architecture serves as a foundation for other services requiring queue functionality and demonstrates HuleEdu's commitment to performance-oriented, well-architected solutions.