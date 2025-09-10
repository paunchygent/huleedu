---
description: Critical anti-patterns that cause production failures and their corrections
globs: 
alwaysApply: true
---
# 077: Service Anti-Patterns

## Infrastructure Client Anti-Patterns

### ❌ Direct Infrastructure Imports
```python
# WRONG
from redis.asyncio import Redis
redis = Redis(host="redis", port=6379)

# RIGHT
from huleedu_service_libs import RedisClient, KafkaBus
from huleedu_service_libs.protocols import RedisClientProtocol
```

### ❌ Missing Lifecycle Management
```python
# WRONG - No lifecycle
@provide(scope=Scope.APP)
async def provide_redis(settings: Settings) -> RedisClientProtocol:
    return RedisClient(client_id="service", redis_url=settings.REDIS_URL)

# RIGHT - Proper lifecycle
@provide(scope=Scope.APP)
async def provide_redis(settings: Settings) -> RedisClientProtocol:
    client = RedisClient(client_id="service", redis_url=settings.REDIS_URL)
    await client.start()  # REQUIRED
    return client
```

## Health Endpoint Anti-Patterns

### ❌ Inconsistent Health Endpoints
```python
# WRONG - PostgreSQL service without database health
@health_bp.route("/healthz")  # Only basic health

# RIGHT - Full three-tier for PostgreSQL services
@health_bp.route("/healthz")
@health_bp.route("/healthz/database")
@health_bp.route("/healthz/database/summary")
```

### ❌ Hardcoded Values
```python
# WRONG
health_response = {"service": "class_management", "environment": "development"}

# RIGHT
health_response = {"service": settings.SERVICE_NAME, "environment": settings.ENVIRONMENT}
```

## Event Processing Anti-Patterns

### ❌ Missing Idempotency
```python
# WRONG
async def handle_message(msg: ConsumerRecord):
    await process_event(envelope)  # Might process duplicates

# RIGHT
@idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
async def handle_message(msg: ConsumerRecord):
    await process_event(envelope)  # Automatically prevents duplicates
```

### ❌ Missing Trace Context
```python
# WRONG
envelope = EventEnvelope(event_type="ESSAY_SUBMITTED", data=event_data)

# RIGHT  
envelope = EventEnvelope(event_type="ESSAY_SUBMITTED", data=event_data)
inject_trace_context(envelope)
```

## Database Anti-Patterns

### ❌ Shared Engine Instances
```python
# WRONG - Shared across DI scopes
@provide(scope=Scope.APP)
async def provide_engine() -> AsyncEngine:
    return create_async_engine(settings.DATABASE_URL)

@provide(scope=Scope.REQUEST) 
async def provide_session(engine: FromDishka[AsyncEngine]) -> AsyncSession:
    return AsyncSession(engine)  # MissingGreenlet errors

# RIGHT - Repository-managed sessions
@provide(scope=Scope.APP)
async def provide_repository(engine: FromDishka[AsyncEngine]) -> RepositoryProtocol:
    return PostgreSQLRepositoryImpl(engine)  # Repository creates own sessionmaker
```

### ❌ Direct Session Usage
```python
# WRONG - Direct session in DI
async def create_student(session: FromDishka[AsyncSession], data: CreateStudentRequest):
    student = Student(**data.model_dump())
    session.add(student)
    await session.commit()  # DetachedInstanceError

# RIGHT - Repository pattern
async def create_student(repo: FromDishka[RepositoryProtocol], data: CreateStudentRequest):
    return await repo.create_student(data)  # Repository manages session lifecycle
```

## Dependency Injection Anti-Patterns

### ❌ Factory Functions Without Scoping
```python
# WRONG - No scoping
@provide
async def create_client() -> RedisClientProtocol:
    return RedisClient()  # New instance per request

# RIGHT - Proper scoping
@provide(scope=Scope.APP)
async def create_client() -> RedisClientProtocol:
    return RedisClient()  # Singleton
```

### ❌ Missing Protocol Contracts
```python
# WRONG - Direct class dependency
async def process(publisher: KafkaEventPublisher):
    await publisher.publish(event)

# RIGHT - Protocol dependency
async def process(publisher: EventPublisherProtocol):
    await publisher.publish(event)
```

## Configuration Anti-Patterns

### ❌ Hardcoded Settings
```python
# WRONG
kafka_client = KafkaBus(bootstrap_servers="kafka:9092")

# RIGHT
kafka_client = KafkaBus(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
```

### ❌ Missing Environment Prefixes
```python
# WRONG - Global settings
class Settings(BaseSettings):
    DB_HOST: str = "localhost"

# RIGHT - Service-specific prefix
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SERVICE_NAME_")
    DB_HOST: str = "localhost"
```

## Testing Anti-Patterns

### ❌ Testing Concrete Implementations
```python
# WRONG
def test_service(real_repository: PostgreSQLRepositoryImpl):
    pass

# RIGHT
def test_service(mock_repository: AsyncMock(spec=RepositoryProtocol)):
    pass
```

### ❌ Missing Prometheus Registry Cleanup
```python
# WRONG - Registry conflicts between tests
def test_metrics():
    metric = Counter("test_counter")  # ValueError on second test

# RIGHT - Registry cleanup
@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
```

## Critical Production Issues

1. **MissingGreenlet**: Use repository-managed sessions, not DI-injected sessions
2. **DetachedInstanceError**: Use `selectinload()` for relationships
3. **Memory Leaks**: Implement proper lifecycle management for infrastructure clients
4. **Duplicate Events**: Use `@idempotent_consumer` for all event handlers
5. **Connection Pool Exhaustion**: Scope dependencies correctly (`APP` vs `REQUEST`)