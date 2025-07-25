"""
Integration test configuration and fixtures for File Service outbox pattern.

This module provides shared fixtures for testing the transactional outbox pattern
including database setup, mock services, and test infrastructure.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from dishka import make_async_container, Provider, Scope, provide
from prometheus_client import REGISTRY
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from huleedu_service_libs.outbox import EventRelayWorker, OutboxProvider
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from huleedu_service_libs.resilience import CircuitBreakerRegistry
from services.file_service.config import Settings
from services.file_service.di import CoreInfrastructureProvider, ServiceImplementationsProvider


@pytest.fixture(autouse=True)
def _clear_prometheus_registry(request):
    """Clear the Prometheus registry before each test to prevent metric conflicts."""
    # Skip clearing for tests marked with no_prometheus_clear
    if request.node.get_closest_marker('no_prometheus_clear'):
        print(f"DEBUG: Skipping Prometheus registry clear for {request.node.name}")
        yield
        return
    
    print(f"DEBUG: Clearing Prometheus registry for {request.node.name}")    
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass  # Ignore if already unregistered
    yield


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings with database connection to test database."""
    import os
    # Set environment variables for test database
    os.environ["FILE_SERVICE_DATABASE_URL"] = (
        "postgresql+asyncpg://huleedu_user:ted5?SUCwef3-JIVres6!DEK@localhost:5439/file_service_db"
    )
    os.environ["FILE_SERVICE_REDIS_URL"] = "redis://localhost:6379/15"  # Use test DB
    
    settings = Settings()
    return settings


@pytest.fixture
def mock_kafka_publisher() -> AsyncMock:
    """Create a mock Kafka publisher for testing."""
    mock = AsyncMock(spec=KafkaPublisherProtocol)
    mock.publish.return_value = None
    return mock


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Create a mock Redis client for testing."""
    mock = AsyncMock(spec=AtomicRedisClientProtocol)
    mock.publish_user_notification.return_value = None
    return mock


class TestInfrastructureProvider(CoreInfrastructureProvider):
    """Test infrastructure provider that uses mocked Kafka and Redis but inherits others."""
    
    def __init__(self, mock_kafka_publisher: AsyncMock, mock_redis_client: AsyncMock):
        super().__init__()
        self._mock_kafka_publisher = mock_kafka_publisher
        self._mock_redis_client = mock_redis_client
    
    @provide(scope=Scope.APP)
    async def provide_kafka_bus(
        self,
        settings: Settings,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> KafkaPublisherProtocol:
        """Provide mocked Kafka publisher for tests (overrides parent)."""
        print("DEBUG: TestInfrastructureProvider.provide_kafka_bus() called - using MOCK!")
        return self._mock_kafka_publisher
    
    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> AtomicRedisClientProtocol:
        """Provide mocked Redis client for tests (overrides parent)."""
        print("DEBUG: TestInfrastructureProvider.provide_redis_client() called - using MOCK!")
        return self._mock_redis_client


@pytest_asyncio.fixture
async def integration_container(
    test_settings: Settings, mock_kafka_publisher: AsyncMock, mock_redis_client: AsyncMock
) -> AsyncGenerator[tuple, None]:
    """
    Create DI container for integration testing with real database and mocked Kafka.
    
    Returns:
        Tuple of (container, engine, session_factory) for test access.
    """
    # Create container with test configuration and mocked Kafka & Redis
    container = make_async_container(
        TestInfrastructureProvider(mock_kafka_publisher, mock_redis_client),
        ServiceImplementationsProvider(),
        OutboxProvider(),
    )
    
    try:
        async with container() as request_container:
            # Get database infrastructure
            engine = await request_container.get(AsyncEngine)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            
            yield container, engine, session_factory
    finally:
        await container.close()


@pytest_asyncio.fixture
async def db_session(
    integration_container: tuple
) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for testing."""
    _, engine, session_factory = integration_container
    
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture
async def event_relay_worker(
    integration_container: tuple, mock_kafka_publisher: AsyncMock
) -> AsyncGenerator[EventRelayWorker, None]:
    """Create and start EventRelayWorker for testing."""
    container, _, _ = integration_container
    
    async with container() as request_container:
        worker = await request_container.get(EventRelayWorker)
        
        # Configure worker for testing
        worker._kafka_publisher = mock_kafka_publisher
        worker._poll_interval = 0.1  # Fast polling for tests
        worker._batch_size = 5
        
        await worker.start()
        
        try:
            yield worker
        finally:
            await worker.stop()


@pytest.fixture
def correlation_id() -> UUID:
    """Generate a test correlation ID."""
    return uuid4()


@pytest.fixture  
def test_batch_id() -> str:
    """Generate a test batch ID."""
    return f"test-batch-{uuid4().hex[:8]}"


@pytest.fixture
def test_file_upload_id() -> str:
    """Generate a test file upload ID."""
    return f"file-upload-{uuid4().hex[:8]}"


@pytest.fixture
def test_user_id() -> str:
    """Generate a test user ID."""
    return f"user-{uuid4().hex[:8]}"