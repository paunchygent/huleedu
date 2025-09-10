---
description: Async patterns, protocols, dependency injection, resource management, and worker service structure
globs: 
alwaysApply: false
---
# 042: Async Patterns and DI

## Protocols
- Define in `protocols.py` using `typing.Protocol`
- Business logic depends on protocols
- Dishka binds implementations

## HuleEduApp Pattern

```python
# app.py
app = HuleEduApp(__name__)
app.container = make_async_container(ServiceProvider())
app.database_engine = create_async_engine(settings.DATABASE_URL)

# Routes with injection
@bp.post("/endpoint")
@inject
async def handler(service: FromDishka[ServiceProtocol]):
    return await service.process()
```

## Kafka Worker Pattern

```python
# worker_main.py
container = make_async_container(ServiceProvider())
async with container() as request_container:
    processor = await request_container.get(EventProcessorProtocol)
    consumer = await request_container.get(KafkaConsumerProtocol)
    
    async for message in consumer.consume():
        await processor.process_message(message)
```

## Repository-Managed Sessions

```python
# CRITICAL: Repository creates own sessionmaker
class PostgreSQLRepositoryImpl:
    def __init__(self, engine: AsyncEngine):
        self.session = async_sessionmaker(engine, expire_on_commit=False)
    
    @asynccontextmanager
    async def session_context(self):
        async with self.session() as session:
            yield session

    async def create(self, data):
        async with self.session_context() as session:
            entity = Entity(**data.model_dump())
            session.add(entity)
            await session.flush()
            await session.refresh(entity, ["relationships"])  # Prevent DetachedInstanceError
            await session.commit()
            return entity
```

## Infrastructure Lifecycle

```python
@provide(scope=Scope.APP)
async def provide_redis_client(settings):
    client = RedisClient(client_id="service", redis_url=settings.REDIS_URL)
    await client.start()  # REQUIRED
    return client

# Cleanup
@app.after_serving
async def shutdown():
    await redis_client.stop()
    await kafka_bus.stop()
```

## Dishka Scopes

```python
class ServiceProvider(Provider):
    # APP scope: Infrastructure singletons
    @provide(scope=Scope.APP)
    async def provide_engine(self, settings) -> AsyncEngine:
        return create_async_engine(settings.DATABASE_URL)
    
    @provide(scope=Scope.APP)
    async def provide_repository(self, engine) -> RepositoryProtocol:
        return PostgreSQLRepositoryImpl(engine)
    
    # REQUEST scope: Per-operation instances
    @provide(scope=Scope.REQUEST)
    async def provide_service(self, repo, publisher) -> ServiceProtocol:
        return ServiceImpl(repo, publisher)

    # REQUEST scope: Correlation context (Quart)
    @provide(scope=Scope.REQUEST)
    def provide_correlation_context(self) -> CorrelationContext:
        """Prefer middleware-populated context; fallback to request extraction."""
        from quart import g, request
        from huleedu_service_libs.error_handling.correlation import (
            CorrelationContext,
            extract_correlation_context_from_request,
        )

        ctx = getattr(g, "correlation_context", None)
        if isinstance(ctx, CorrelationContext):
            return ctx
        return extract_correlation_context_from_request(request)
```

## Key Patterns

**Eager Loading**:
```python
await session.refresh(entity, ["relationships"])
```

**Concurrent Control**:
```python
semaphore = asyncio.Semaphore(10)
async with semaphore:
    await operation()
```

**Batch Operations**:
```python
async with self.session_context() as session:
    for item in batch:
        session.add(Entity(**item))
    await session.flush()
    await session.commit()
```

## Issue Prevention

1. **MissingGreenlet**: Repository-managed sessions
2. **DetachedInstanceError**: `selectinload()` or `refresh()`
3. **Pool Exhaustion**: Correct DI scopes (APP/REQUEST)
4. **Resource Leaks**: `start()`/`stop()` lifecycle
5. **Deadlocks**: Semaphore concurrency limits
