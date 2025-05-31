# HuleEdu Developer Technical Reference

**Internal Engineering Documentation**  
**Target Audience**: Development Team  
**Last Updated**: 2025-01-07

## Architecture Overview

HuleEdu implements an event-driven microservice architecture using Domain-Driven Design principles. Each service owns its bounded context, communicates asynchronously via Kafka events, and exposes HTTP APIs for synchronous operations.

### Service Communication Patterns

```
┌─────────────────┐    HTTP    ┌─────────────────┐
│  Batch Service  │ ──────────▶│ Content Service │
└─────────────────┘            └─────────────────┘
         │
         │ Kafka Events
         ▼
┌─────────────────┐    Kafka   ┌─────────────────┐
│Essay Lifecycle │ ◄─────────▶│Spell Checker    │
│    Service      │            │    Service      │
└─────────────────┘            └─────────────────┘
         │                              │
         │ HTTP                         │ HTTP
         ▼                              ▼
┌─────────────────┐                ┌─────────────────┐
│ Content Service │                │ Content Service │
└─────────────────┘                └─────────────────┘
```

## Tech Stack Rationale

### Core Framework Decisions

**Quart over FastAPI**: Chosen for native async/await support without thread pools. Better integration with aiokafka and aiohttp client libraries.

**PDM over Poetry**: Superior monorepo support, faster dependency resolution, better lock file format, and simpler configuration.

**Dishka over dependency-injector**: Cleaner async support, better typed protocol integration, simpler provider patterns.

**aiokafka over confluent-kafka**: Native asyncio support, no thread management overhead, better integration with Quart.

### Database & Persistence

**SQLite for ELS**: Embedded database reduces operational complexity for single-service state. Production migration to PostgreSQL planned.

**Filesystem for Content Service**: Simplifies MVP implementation. Cloud storage backend (S3) planned for production.

**No ORM**: Direct SQL with aiosqlite for ELS provides better control over queries and migrations.

## Service Architecture Patterns

### HTTP Service Pattern (Quart)

All HTTP services follow the Blueprint pattern:

```python
# app.py - Lean application setup
app = Quart(__name__)
container = make_async_container(ServiceProvider())
QuartDishka(app=app, container=container)

# Register blueprints
app.register_blueprint(health_bp)
app.register_blueprint(domain_bp)

# api/health_routes.py - Standard health endpoints
health_bp = Blueprint('health_routes', __name__)

@health_bp.route("/healthz")
async def health_check() -> Response:
    return jsonify({"status": "ok"}), 200

@health_bp.route("/metrics") 
async def metrics() -> Response:
    return Response(generate_latest(), content_type=CONTENT_TYPE_LATEST)
```

### Worker Service Pattern (Kafka)

Event-driven services use the protocol-based pattern:

```python
# worker_main.py - Service lifecycle
async def main():
    container = make_async_container(ServiceProvider())
    async with container() as request_container:
        processor = await request_container.get(EventProcessor)
        async with kafka_clients() as (consumer, producer):
            # Message consumption loop

# event_processor.py - Business logic
async def process_single_message(
    msg: ConsumerRecord,
    text_extractor: TextExtractorProtocol,
    content_client: ContentClientProtocol,
    event_publisher: EventPublisherProtocol,
) -> bool:
    # Protocol-based message processing
```

### Dual-Mode Service Pattern (ELS)

Services requiring both HTTP API and Kafka worker:

```python
# app.py - HTTP entry point
# worker_main.py - Kafka consumer entry point
# Shared: protocols.py, di.py, implementations/
```

## Dependency Injection Architecture

### Protocol-First Design

All services define behavioral contracts using `typing.Protocol`:

```python
# protocols.py
class ContentClientProtocol(Protocol):
    async def store_content(self, content_bytes: bytes) -> str: ...
    async def fetch_content(self, storage_id: str) -> bytes: ...

class EventPublisherProtocol(Protocol):
    async def publish_event(self, event: EventEnvelope[T]) -> None: ...
```

### Provider Pattern

Each service implements a Dishka provider:

```python
# di.py
class ServiceProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_content_client(
        self, session: ClientSession, settings: Settings
    ) -> ContentClientProtocol:
        return DefaultContentClient(session, settings)

    @provide(scope=Scope.REQUEST)
    async def provide_kafka_producer(self) -> AIOKafkaProducer:
        producer = AIOKafkaProducer(bootstrap_servers=settings.KAFKA_SERVERS)
        await producer.start()
        return producer
```

### Scope Management

- **APP**: Stateless singletons (settings, HTTP sessions)
- **REQUEST**: Per-operation instances (Kafka producers, database connections)

## Event System Architecture

### EventEnvelope Standard

All events use the standardized envelope:

```python
@dataclass
class EventEnvelope(BaseModel, Generic[T_EventData]):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str  # "huleedu.essay.spellcheck.requested.v1"
    event_timestamp: datetime
    source_service: str
    correlation_id: Optional[UUID] = None
    schema_version: int = 1
    data: T_EventData
```

### Topic Naming Convention

Topics follow the pattern: `{project}.{domain}.{entity}.{action}.v{version}`

```python
# common_core/enums.py
def topic_name(event: ProcessingEvent) -> str:
    mapping = {
        ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED: "huleedu.essay.spellcheck.requested.v1",
        ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED: "huleedu.essay.spellcheck.completed.v1",
    }
    return mapping[event]
```

### Event Data Patterns

Events carry minimal data with storage references:

```python
class SpellcheckRequestedDataV1(BaseEventData):
    essay_id: str
    text_storage_id: str  # Reference to Content Service
    entity: EntityReference
    system_metadata: SystemProcessingMetadata
```

## Configuration Management

### Standardized Settings Pattern

All services use Pydantic BaseSettings:

```python
# config.py
class Settings(BaseSettings):
    LOG_LEVEL: str = "INFO"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    HTTP_PORT: int = 8000
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SERVICE_NAME_",
        extra="ignore"
    )

settings = Settings()
```

### Environment Variable Conventions

- Prefix: `{SERVICE_NAME}_` (e.g., `CONTENT_SERVICE_`, `BATCH_SERVICE_`)
- Ports: HTTP_PORT, PROMETHEUS_PORT, METRICS_PORT
- External URLs: `{TARGET_SERVICE}_URL`

## Testing Architecture

### Test Categories

1. **Unit Tests**: Protocol-based with mocks
2. **Contract Tests**: Pydantic schema validation
3. **Integration Tests**: Service-to-service communication
4. **End-to-End Tests**: Full workflow validation

### Protocol Testing Pattern

```python
async def test_process_message_success(
    mock_text_extractor: AsyncMock,
    mock_content_client: AsyncMock,
    mock_event_publisher: AsyncMock,
):
    # Arrange
    message = create_test_message()
    
    # Act
    result = await process_single_message(
        message,
        text_extractor=mock_text_extractor,
        content_client=mock_content_client,
        event_publisher=mock_event_publisher,
    )
    
    # Assert
    assert result is True
    mock_event_publisher.publish_event.assert_called_once()
```

### Contract Testing

```python
def test_event_serialization_roundtrip():
    event = EventEnvelope[SpellcheckRequestedDataV1](
        event_type="test.event.v1",
        source_service="test",
        data=SpellcheckRequestedDataV1(...)
    )
    
    serialized = json.dumps(event.model_dump(mode="json"))
    deserialized = EventEnvelope[SpellcheckRequestedDataV1].model_validate(
        json.loads(serialized)
    )
    
    assert deserialized.event_id == event.event_id
```

## Service-Specific Implementation Notes

### Content Service

- **Storage**: Local filesystem with UUID-based file naming
- **API**: Simple POST/GET for binary content
- **No authentication**: Internal service only
- **Volume persistence**: Docker volume for data retention

### Spell Checker Service

- **Algorithm**: L2 error dictionary + pyspellchecker
- **Architecture**: Clean architecture with protocol implementations
- **Performance**: Single-threaded async processing
- **Error handling**: Comprehensive with failure event publishing

### Batch Orchestrator Service

- **Responsibility**: Workflow orchestration via events
- **Repository**: In-memory with planned persistence
- **API**: RESTful batch registration and status
- **Event coordination**: Central hub for batch lifecycle

### Essay Lifecycle Service

- **State management**: SQLite with essay state tracking
- **Dual mode**: HTTP API + Kafka worker
- **Batch coordination**: Tracks essay readiness across batches
- **Database schema**: Auto-migration on startup

## Development Patterns

### Import Conventions

**Absolute imports for containerized services**:
```python
# ✅ CORRECT - Works in containers
from config import settings
from protocols import ServiceProtocol

# ❌ FORBIDDEN - Breaks in containers  
from .config import settings
from .protocols import ServiceProtocol
```

### Error Handling Patterns

```python
# Domain-specific exceptions
class ContentNotFoundError(Exception): ...
class SpellCheckError(Exception): ...

# Protocol error handling
async def safe_content_fetch(client: ContentClientProtocol, id: str) -> Optional[bytes]:
    try:
        return await client.fetch_content(id)
    except ContentNotFoundError:
        logger.warning(f"Content not found: {id}")
        return None
```

### Logging Patterns

```python
# Centralized logging with correlation IDs
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger

configure_service_logging("service-name", log_level=settings.LOG_LEVEL)
logger = create_service_logger("component-name")

# Log with correlation ID
logger.info("Processing message", extra={"correlation_id": correlation_id})
```

## Performance Considerations

### Async Context Managers

Resource management for Kafka clients:

```python
@asynccontextmanager
async def kafka_clients() -> AsyncIterator[tuple[AIOKafkaConsumer, AIOKafkaProducer]]:
    consumer = AIOKafkaConsumer(...)
    producer = AIOKafkaProducer(...)
    
    await consumer.start()
    await producer.start()
    
    try:
        yield consumer, producer
    finally:
        await consumer.stop()
        await producer.stop()
```

### Connection Pooling

HTTP client session reuse:

```python
# Scoped to APP in DI container
@provide(scope=Scope.APP)
def provide_http_session(self) -> ClientSession:
    return ClientSession(
        timeout=ClientTimeout(total=30),
        connector=TCPConnector(limit=100)
    )
```

## Monitoring & Observability

### Metrics Endpoints

All services expose Prometheus metrics:

```python
@blueprint.route("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), content_type=CONTENT_TYPE_LATEST)
```

### Health Checks

Standardized health check implementation:

```python
@blueprint.route("/healthz")  
async def health_check() -> Response:
    # Service-specific health validation
    return jsonify({
        "status": "ok",
        "service": settings.SERVICE_NAME,
        "timestamp": datetime.utcnow().isoformat()
    })
```

### Correlation ID Tracking

End-to-end request tracking:

```python
# Generate or extract correlation ID
correlation_id = uuid4() if not request_correlation_id else request_correlation_id

# Pass through all service calls and events
event = EventEnvelope(
    correlation_id=correlation_id,
    data=event_data
)
```

## Docker & Deployment

### Multi-stage Build Pattern

Services use optimized Dockerfiles:

```dockerfile
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PDM_USE_VENV=false

# Copy dependencies
COPY common_core/ /app/common_core/
COPY services/libs/ /app/services/libs/
COPY services/{service}/ /app/services/{service}/

WORKDIR /app/services/{service}
RUN pdm install --prod

USER appuser
CMD ["pdm", "run", "start"]
```

### Service Dependencies

Docker Compose dependency hierarchy:

1. Infrastructure: zookeeper, kafka
2. Topics: kafka_topic_setup  
3. Core: content_service
4. Dependent: all other services

## Code Quality Standards

### File Size Limits

- **Python files**: 400 lines maximum
- **Line length**: 100 characters
- **Enforcement**: CI validation with `scripts/loc_guard.sh`

### Type Safety

- **MyPy**: Strict mode for new services
- **Type annotations**: Required for all public APIs
- **Protocol usage**: Dependency injection interfaces

### Linting & Formatting

- **Ruff**: Formatting and linting
- **Configuration**: Root `pyproject.toml`
- **Auto-fix**: `pdm run lint-fix`

## Security Considerations

### Current Implementation

- **Internal services**: No authentication between services
- **Container isolation**: Services run as non-root users
- **Network isolation**: Docker internal network
- **Input validation**: Pydantic model validation

### Production Requirements

- **Service authentication**: mTLS or JWT tokens
- **Input sanitization**: File upload validation
- **Audit logging**: Security event tracking
- **Secret management**: External secret store

## Future Architecture Evolution

### Phase 2 Additions

- **AI Processing Services**: NLP, feedback generation, comparative judgement
- **Gateway Services**: API gateway, load balancing
- **Persistence**: PostgreSQL for production workloads
- **Caching**: Redis for frequently accessed data

### Scalability Preparations

- **Horizontal scaling**: Stateless service design
- **Database sharding**: Multi-tenant data partitioning  
- **Event sourcing**: Immutable event store
- **CQRS**: Separate read/write models

## Troubleshooting Common Issues

### Import Resolution

```bash
# Container import issues
docker-compose exec service_name python -c "from config import settings"

# MyPy import errors  
mypy --config-file pyproject.toml services/service_name/
```

### Kafka Connection

```bash
# Topic verification
docker-compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --list

# Consumer lag monitoring
docker-compose logs spell_checker_service --tail=20
```

### Service Health

```bash
# Health check validation
curl -f http://localhost:8001/healthz

# Metrics verification
curl -f http://localhost:8001/metrics | grep -E "(http_requests|service_)"
```

---

**Note**: This documentation reflects the current implementation state. Update as services evolve and new patterns emerge. 