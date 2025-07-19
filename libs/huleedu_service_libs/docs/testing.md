# Testing Guidelines

Protocol-based mocking and comprehensive testing patterns for HuleEdu service libraries.

## Overview

This guide covers testing strategies for services using HuleEdu service libraries, focusing on protocol-based mocking, integration testing, and test patterns that align with our dependency injection architecture.

### Testing Philosophy

- **Protocol-Based Mocking**: Mock interfaces, not implementations
- **Explicit Dependencies**: Use real dependency injection in tests
- **Integration Coverage**: Test service interactions and infrastructure
- **Test Isolation**: Each test manages its own dependencies
- **Realistic Scenarios**: Test real failure modes and edge cases

## Protocol-Based Mocking

### Basic Mock Setup

```python
from unittest.mock import AsyncMock
from huleedu_service_libs.protocols import (
    KafkaPublisherProtocol,
    RedisClientProtocol,
    AtomicRedisClientProtocol
)

@pytest.fixture
def mock_kafka_publisher():
    """Mock Kafka publisher with protocol specification."""
    mock = AsyncMock(spec=KafkaPublisherProtocol)
    mock.publish.return_value = None
    return mock

@pytest.fixture  
def mock_redis_client():
    """Mock Redis client with protocol specification."""
    mock = AsyncMock(spec=RedisClientProtocol)
    mock.set_if_not_exists.return_value = True
    mock.get.return_value = None
    mock.setex.return_value = True
    mock.delete_key.return_value = 1
    mock.ping.return_value = True
    return mock

@pytest.fixture
def mock_atomic_redis():
    """Mock atomic Redis operations."""
    mock = AsyncMock(spec=AtomicRedisClientProtocol)
    mock.watch.return_value = True
    mock.multi.return_value = True
    mock.exec.return_value = ["OK"]
    mock.unwatch.return_value = True
    return mock
```

### Service Testing with Mocks

```python
# Test service implementation with mocked dependencies
from implementations.content_service_impl import ContentServiceImpl

async def test_create_content_success(
    mock_repository,
    mock_kafka_publisher,
    mock_redis_client
):
    """Test successful content creation."""
    # Arrange
    service = ContentServiceImpl(
        repository=mock_repository,
        kafka_bus=mock_kafka_publisher,
        redis_client=mock_redis_client
    )
    
    content_data = {"title": "Test Content", "user_id": "user123"}
    expected_content = Content(id="content123", title="Test Content")
    
    # Configure mocks
    mock_redis_client.set_if_not_exists.return_value = True  # Not duplicate
    mock_repository.create_content.return_value = expected_content
    
    # Act
    result = await service.create_content(content_data)
    
    # Assert
    assert result.id == "content123"
    assert result.title == "Test Content"
    
    # Verify interactions
    mock_redis_client.set_if_not_exists.assert_called_once()
    mock_repository.create_content.assert_called_once_with(content_data)
    mock_kafka_publisher.publish.assert_called_once()
```

### Error Handling Tests

```python
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from common_core.enums.error_enum import ErrorCode

async def test_create_content_duplicate(
    mock_repository,
    mock_kafka_publisher, 
    mock_redis_client
):
    """Test duplicate content handling."""
    # Arrange
    service = ContentServiceImpl(
        repository=mock_repository,
        kafka_bus=mock_kafka_publisher,
        redis_client=mock_redis_client
    )
    
    # Configure for duplicate scenario
    mock_redis_client.set_if_not_exists.return_value = False  # Duplicate detected
    existing_content = Content(id="existing123", title="Test Content")
    mock_repository.get_content_by_title.return_value = existing_content
    
    # Act & Assert
    result = await service.create_content({"title": "Test Content", "user_id": "user123"})
    
    # Should return existing content
    assert result.id == "existing123"
    
    # Should not create new content or publish event
    mock_repository.create_content.assert_not_called()
    mock_kafka_publisher.publish.assert_not_called()
```

## Error Handling Testing

### Custom Test Utilities

```python
# test_helpers.py
from contextlib import asynccontextmanager
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from common_core.enums.error_enum import ErrorCode

@asynccontextmanager
async def assert_raises_huleedu_error(
    error_code: ErrorCode,
    service: str = None,
    operation: str = None,
    message_contains: str = None
):
    """Assert that HuleEduError is raised with specific conditions."""
    try:
        yield
        pytest.fail(f"Expected HuleEduError with code {error_code}")
    except HuleEduError as e:
        assert e.error_detail.error_code == error_code
        
        if service:
            assert e.error_detail.service == service
        if operation:
            assert e.error_detail.operation == operation
        if message_contains:
            assert message_contains in e.error_detail.message

class ErrorDetailMatcher:
    """Helper for asserting error detail properties."""
    def __init__(
        self,
        error_code: ErrorCode = None,
        service: str = None,
        operation: str = None,
        message_contains: str = None
    ):
        self.error_code = error_code
        self.service = service
        self.operation = operation
        self.message_contains = message_contains
    
    def matches(self, error_detail) -> bool:
        """Check if error detail matches criteria."""
        if self.error_code and error_detail.error_code != self.error_code:
            return False
        if self.service and error_detail.service != self.service:
            return False
        if self.operation and error_detail.operation != self.operation:
            return False
        if self.message_contains and self.message_contains not in error_detail.message:
            return False
        return True
```

### Using Test Utilities

```python
async def test_content_not_found(mock_repository, mock_kafka_publisher, mock_redis_client):
    """Test content not found scenario."""
    service = ContentServiceImpl(
        repository=mock_repository,
        kafka_bus=mock_kafka_publisher,
        redis_client=mock_redis_client
    )
    
    # Configure mock to return None
    mock_repository.get_content.return_value = None
    
    # Test with custom assertion helper
    async with assert_raises_huleedu_error(
        error_code=ErrorCode.RESOURCE_NOT_FOUND,
        service="content_service",
        operation="get_content"
    ):
        await service.get_content("nonexistent_id")

async def test_validation_error_details():
    """Test validation error details."""
    try:
        await service.validate_content({"invalid": "data"})
        pytest.fail("Expected validation error")
    except HuleEduError as e:
        matcher = ErrorDetailMatcher(
            error_code=ErrorCode.VALIDATION_ERROR,
            message_contains="required field"
        )
        assert matcher.matches(e.error_detail)
```

## Idempotency Testing

### Idempotency Decorator Testing

```python
from huleedu_service_libs.idempotency_v2 import idempotent_consumer_v2, IdempotencyConfig

async def test_idempotent_processing_first_time(mock_redis_client):
    """Test that event is processed on first occurrence."""
    config = IdempotencyConfig(
        service_name="test-service",
        enable_debug_logging=True
    )
    
    # Configure Redis for first-time processing
    mock_redis_client.set_if_not_exists.return_value = True
    
    process_called = False
    
    @idempotent_consumer_v2(redis_client=mock_redis_client, config=config)
    async def process_event(msg):
        nonlocal process_called
        process_called = True
        return "processed"
    
    # Create mock Kafka message
    msg = create_mock_kafka_message(event_type="test.event", event_id="123")
    
    result = await process_event(msg)
    
    assert process_called
    assert result == "processed"
    mock_redis_client.set_if_not_exists.assert_called_once()

async def test_idempotent_processing_duplicate(mock_redis_client):
    """Test that duplicate event is skipped."""
    config = IdempotencyConfig(service_name="test-service")
    
    # Configure Redis for duplicate detection
    mock_redis_client.set_if_not_exists.return_value = False
    
    process_called = False
    
    @idempotent_consumer_v2(redis_client=mock_redis_client, config=config)
    async def process_event(msg):
        nonlocal process_called
        process_called = True
    
    msg = create_mock_kafka_message(event_type="test.event", event_id="123")
    await process_event(msg)
    
    assert not process_called  # Should be skipped
    mock_redis_client.set_if_not_exists.assert_called_once()
    mock_redis_client.delete_key.assert_not_called()
```

### Mock Kafka Message Factory

```python
from aiokafka import ConsumerRecord
from common_core.events.envelope import EventEnvelope

def create_mock_kafka_message(
    event_type: str = "test.event",
    event_id: str = "test-123",
    source_service: str = "test-service",
    data: dict = None
) -> ConsumerRecord:
    """Create mock Kafka message for testing."""
    envelope = EventEnvelope(
        event_id=event_id,
        event_type=event_type,
        source_service=source_service,
        data=data or {"test": "data"}
    )
    
    return ConsumerRecord(
        topic="test-topic",
        partition=0,
        offset=1,
        timestamp=None,
        timestamp_type=None,
        key=None,
        value=envelope.model_dump_json().encode(),
        headers=None,
        checksum=None,
        serialized_key_size=None,
        serialized_value_size=None,
        serialized_header_size=None
    )
```

## Integration Testing

### Redis Integration Tests

```python
import pytest
from testcontainers.redis import RedisContainer
from huleedu_service_libs import RedisClient

@pytest.fixture(scope="session")
async def redis_container():
    """Start Redis container for integration tests."""
    with RedisContainer() as redis:
        yield redis

@pytest.fixture
async def redis_client(redis_container):
    """Create Redis client connected to test container."""
    client = RedisClient(
        client_id="test-redis",
        redis_url=redis_container.get_connection_url()
    )
    await client.start()
    try:
        yield client
    finally:
        await client.stop()

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
    msg1 = create_mock_kafka_message(event_id="test-event-123")
    msg2 = create_mock_kafka_message(event_id="test-event-123")  # Same ID
    
    # Process first message
    result1 = await process_event(msg1)
    assert call_count == 1
    assert result1 == "processed-1"
    
    # Process duplicate - should be skipped
    result2 = await process_event(msg2)
    assert call_count == 1  # No additional processing
    assert result2 is None  # Idempotency decorator returns None for duplicates
```

### Kafka Integration Tests

```python
from testcontainers.kafka import KafkaContainer
from huleedu_service_libs import KafkaBus

@pytest.fixture(scope="session")
async def kafka_container():
    """Start Kafka container for integration tests."""
    with KafkaContainer() as kafka:
        yield kafka

@pytest.fixture
async def kafka_bus(kafka_container):
    """Create Kafka bus connected to test container."""
    bus = KafkaBus(
        client_id="test-kafka",
        bootstrap_servers=kafka_container.get_bootstrap_server()
    )
    await bus.start()
    try:
        yield bus
    finally:
        await bus.stop()

async def test_event_publishing(kafka_bus):
    """Test event publishing with real Kafka."""
    envelope = EventEnvelope(
        event_type="test.content.created",
        source_service="test-service",
        data={"content_id": "123", "title": "Test Content"}
    )
    
    # Publishing should not raise exceptions
    await kafka_bus.publish("test-events", envelope)
    
    # Verify event structure (consumer would receive this)
    assert envelope.event_type == "test.content.created"
    assert envelope.source_service == "test-service"
    assert envelope.data["content_id"] == "123"
```

## Database Testing

### Repository Testing

```python
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
async def postgres_container():
    """Start PostgreSQL container for integration tests."""
    with PostgresContainer("postgres:15") as postgres:
        yield postgres

@pytest.fixture
async def test_engine(postgres_container):
    """Create test database engine."""
    engine = create_async_engine(postgres_container.get_connection_url())
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    try:
        yield engine
    finally:
        await engine.dispose()

async def test_content_repository_operations(test_engine):
    """Test repository with real database."""
    repository = ContentRepositoryImpl(test_engine, {})  # Empty metrics dict
    
    # Test create
    content_data = {"title": "Test Content", "user_id": "user123"}
    content = await repository.create_content(content_data)
    
    assert content.id is not None
    assert content.title == "Test Content"
    assert content.user_id == "user123"
    
    # Test retrieve
    retrieved = await repository.get_content(content.id)
    assert retrieved is not None
    assert retrieved.title == content.title
    
    # Test not found
    not_found = await repository.get_content("nonexistent")
    assert not_found is None
```

## HTTP Route Testing

### Quart Route Testing

```python
from quart.testing import QuartClient
from huleedu_service_libs import HuleEduApp
from unittest.mock import AsyncMock

@pytest.fixture
def mock_content_service():
    """Mock content service for route testing."""
    mock = AsyncMock()
    mock.create_content.return_value = Content(id="123", title="Test")
    mock.get_content.return_value = Content(id="123", title="Test")
    return mock

@pytest.fixture
async def test_app(mock_content_service):
    """Create test app with mocked dependencies."""
    app = HuleEduApp(__name__)
    app.config['TESTING'] = True
    
    # Mock infrastructure
    app.database_engine = AsyncMock()
    app.container = AsyncMock()
    
    # Configure DI container to return mocks
    async def get_dependency(dependency_type):
        if dependency_type == ContentServiceProtocol:
            return mock_content_service
        return AsyncMock()
    
    app.container.get.side_effect = get_dependency
    
    # Register routes
    from api.content_routes import content_bp
    app.register_blueprint(content_bp)
    
    async with app.test_app():
        yield app

async def test_create_content_endpoint(test_app, mock_content_service):
    """Test content creation endpoint."""
    client: QuartClient = test_app.test_client()
    
    response = await client.post("/content", json={
        "title": "Test Content",
        "user_id": "user123"
    })
    
    assert response.status_code == 200
    data = await response.get_json()
    assert data["content_id"] == "123"
    
    # Verify service was called
    mock_content_service.create_content.assert_called_once()

async def test_get_content_not_found(test_app, mock_content_service):
    """Test content not found scenario."""
    # Configure mock to return None
    mock_content_service.get_content.return_value = None
    
    client: QuartClient = test_app.test_client()
    response = await client.get("/content/nonexistent")
    
    # Should return 404 due to error handling
    assert response.status_code == 404
    
    data = await response.get_json()
    assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
```

## Test Organization

### Test File Structure

```
tests/
├── unit/                          # Fast, isolated unit tests
│   ├── test_content_service.py
│   ├── test_content_repository.py
│   └── test_error_handling.py
├── integration/                   # Tests with real infrastructure
│   ├── test_redis_integration.py
│   ├── test_kafka_integration.py
│   └── test_database_integration.py
├── api/                          # HTTP endpoint tests
│   ├── test_content_routes.py
│   └── test_health_routes.py
├── fixtures/                     # Shared test fixtures
│   ├── mock_fixtures.py
│   └── container_fixtures.py
└── helpers/                      # Test utilities
    ├── assertions.py
    └── factories.py
```

### Pytest Configuration

```python
# conftest.py - Global test configuration
import pytest
import asyncio
from unittest.mock import AsyncMock

# Configure asyncio for tests
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

# Mark integration tests
pytest_plugins = ["fixtures.mock_fixtures", "fixtures.container_fixtures"]

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests requiring containers"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as fast unit tests"
    )
```

## Best Practices

1. **Protocol-Based Mocking**: Always specify protocols in AsyncMock
2. **Realistic Test Data**: Use factories for consistent test data
3. **Integration Coverage**: Test real infrastructure interactions
4. **Error Path Testing**: Test all error scenarios and edge cases
5. **Idempotency Testing**: Verify duplicate handling works correctly
6. **Resource Cleanup**: Properly cleanup containers and connections
7. **Test Isolation**: Each test manages its own dependencies
8. **Async Throughout**: Use async/await in all test code

## Anti-Patterns to Avoid

1. **Implementation Mocking**: Don't mock concrete classes directly
2. **Shared Mutable State**: Avoid shared fixtures that modify state
3. **Missing Error Tests**: Test error paths as thoroughly as success paths
4. **Synchronous Testing**: Don't mix sync and async test patterns
5. **Container Leaks**: Always cleanup test containers properly
6. **Generic Assertions**: Use specific assertions for error conditions
7. **Test Dependencies**: Tests should not depend on execution order
8. **Missing Integration**: Include tests with real infrastructure components