"""
Integration test configuration for File Service outbox pattern.

Provides minimal, focused testcontainer-based fixtures for testing the transactional
outbox pattern with isolated PostgreSQL containers. Follows established project patterns
from batch_orchestrator_service and cj_assessment_service.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Generator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from huleedu_service_libs.outbox import EventRelayWorker, OutboxProvider
from huleedu_service_libs.outbox.models import EventOutbox
from huleedu_service_libs.outbox.protocols import OutboxRepositoryProtocol
from huleedu_service_libs.outbox.relay import OutboxSettings
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from prometheus_client import REGISTRY
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from services.file_service.config import Settings
from services.file_service.implementations.event_publisher_impl import DefaultEventPublisher
from services.file_service.implementations.outbox_manager import OutboxManager
from services.file_service.protocols import EventPublisherProtocol


@pytest.fixture(autouse=True)
def _clear_prometheus_registry() -> Any:
    """Clear the Prometheus registry before each test to prevent metric conflicts."""
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass  # Ignore if already unregistered
    yield


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


class MinimalOutboxTestProvider(Provider):
    """
    Minimal DI provider focused ONLY on outbox testing dependencies.

    Provides only what's needed for outbox integration tests:
    - Real PostgreSQL database and outbox repository
    - Real OutboxManager and EventPublisher implementations
    - Mocked external services (Kafka, Redis)
    - Essential settings
    """

    def __init__(
        self,
        engine: AsyncEngine,
        kafka_publisher: AsyncMock,
        redis_client: AsyncMock,
    ):
        super().__init__()
        self._engine = engine
        self._kafka_publisher = kafka_publisher
        self._redis_client = redis_client

        # Create minimal test settings
        self._settings = Settings()
        self._settings.SERVICE_NAME = "file-service"
        self._settings.ESSAY_CONTENT_PROVISIONED_TOPIC = "file.essay.content.provisioned.v1"
        self._settings.ESSAY_VALIDATION_FAILED_TOPIC = "file.essay.validation.failed.v1"
        self._settings.BATCH_FILE_ADDED_TOPIC = "file.batch.file.added.v1"
        self._settings.BATCH_FILE_REMOVED_TOPIC = "file.batch.file.removed.v1"

    @provide(scope=Scope.APP)
    async def provide_engine(self) -> AsyncEngine:
        """Provide test database engine."""
        return self._engine

    @provide(scope=Scope.APP)
    def provide_kafka_publisher(self) -> KafkaPublisherProtocol:
        """Provide mock Kafka publisher."""
        return self._kafka_publisher

    @provide(scope=Scope.APP)
    def provide_redis_client(self) -> AtomicRedisClientProtocol:
        """Provide mock Redis client."""
        return self._redis_client

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide test settings."""
        return self._settings

    @provide(scope=Scope.APP)
    def provide_service_name(self) -> str:
        """Provide service name for OutboxProvider dependency."""
        return self._settings.SERVICE_NAME

    @provide(scope=Scope.APP)
    def provide_outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> OutboxManager:
        """Provide OutboxManager with real database and mocked Redis."""
        return OutboxManager(outbox_repository, redis_client, settings)

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self,
        outbox_manager: OutboxManager,
        settings: Settings,
        redis_client: AtomicRedisClientProtocol,
    ) -> EventPublisherProtocol:
        """Provide EventPublisher with outbox pattern."""
        return DefaultEventPublisher(outbox_manager, settings, redis_client)

    @provide(scope=Scope.APP)
    def provide_event_relay_worker(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        kafka_publisher: KafkaPublisherProtocol,
        settings: Settings,
    ) -> EventRelayWorker:
        """Provide event relay worker for testing outbox processing."""
        outbox_settings = OutboxSettings(
            poll_interval_seconds=0.1,  # Fast polling for tests
            batch_size=5,
            max_retries=3,
        )

        return EventRelayWorker(
            outbox_repository=outbox_repository,
            kafka_bus=kafka_publisher,
            settings=outbox_settings,
            service_name=settings.SERVICE_NAME,
        )


@pytest.mark.asyncio
class TestFileServiceOutboxPatternIntegration:
    """
    Base class for File Service outbox integration tests with testcontainers.

    Provides isolated PostgreSQL testcontainer environment for testing
    the transactional outbox pattern with real database operations.
    """

    @pytest.fixture(scope="class")
    def postgres_container(self) -> PostgresContainer:
        """Start isolated PostgreSQL testcontainer for integration tests."""
        container = PostgresContainer("postgres:15")
        container.start()
        yield container
        container.stop()

    @pytest.fixture
    async def test_engine(
        self, postgres_container: PostgresContainer
    ) -> AsyncGenerator[AsyncEngine, None]:
        """Create test database engine with proper cleanup."""
        connection_url = postgres_container.get_connection_url()
        # Convert to asyncpg URL following established pattern
        connection_url = connection_url.replace("+psycopg2://", "+asyncpg://")
        connection_url = connection_url.replace("postgresql://", "postgresql+asyncpg://")

        engine = create_async_engine(connection_url, echo=False)

        try:
            # Create outbox table for testing
            async with engine.begin() as conn:
                await conn.run_sync(EventOutbox.metadata.create_all)

            yield engine
        finally:
            # Proper engine disposal
            await engine.dispose()

    @pytest.fixture
    async def db_session_factory(
        self, test_engine: AsyncEngine
    ) -> async_sessionmaker[AsyncSession]:
        """Create session factory for database access."""
        return async_sessionmaker(test_engine, expire_on_commit=False)

    @pytest.fixture
    async def db_session(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> AsyncGenerator[AsyncSession, None]:
        """Create database session with automatic cleanup."""
        async with db_session_factory() as session:
            yield session

    @pytest.fixture
    def mock_kafka_publisher(self) -> AsyncMock:
        """Create mock Kafka publisher with tracking capabilities."""
        mock = AsyncMock(spec=KafkaPublisherProtocol)
        mock.publish = AsyncMock(return_value=None)
        mock.published_events = []  # Track published events

        # Side effect to track calls
        async def track_publish(**kwargs: Any) -> None:
            mock.published_events.append(kwargs)

        mock.publish.side_effect = track_publish
        return mock

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock(spec=AtomicRedisClientProtocol)
        mock.publish_user_notification.return_value = None
        mock.lpush = AsyncMock(return_value=None)
        return mock

    @asynccontextmanager
    async def create_test_container(
        self,
        engine: AsyncEngine,
        kafka_publisher: AsyncMock,
        redis_client: AsyncMock,
    ) -> AsyncGenerator[AsyncContainer, None]:
        """Create minimal DI container focused on outbox testing."""
        container = make_async_container(
            MinimalOutboxTestProvider(engine, kafka_publisher, redis_client),
            OutboxProvider(),
        )
        try:
            yield container
        finally:
            await container.close()

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Generate test correlation ID."""
        return uuid4()

    @pytest.fixture
    def test_batch_id(self) -> str:
        """Generate test batch ID."""
        return f"test-batch-{uuid4().hex[:8]}"

    @pytest.fixture
    def test_file_upload_id(self) -> str:
        """Generate test file upload ID."""
        return f"file-upload-{uuid4().hex[:8]}"

    @pytest.fixture
    def test_user_id(self) -> str:
        """Generate test user ID."""
        return f"user-{uuid4().hex[:8]}"

    @pytest.fixture(autouse=True)
    async def clean_outbox_table(self, test_engine: AsyncEngine) -> AsyncGenerator[None, None]:
        """Clean the outbox table before and after each test for isolation."""
        # Clean before test
        async with test_engine.begin() as conn:
            await conn.execute(delete(EventOutbox))

        yield

        # Clean after test
        async with test_engine.begin() as conn:
            await conn.execute(delete(EventOutbox))

    async def wait_for_condition(
        self,
        condition: Callable[[], bool],
        timeout: float = 2.0,
        interval: float = 0.05,
    ) -> None:
        """Wait for a condition to become true with timeout."""
        start_time = asyncio.get_event_loop().time()
        while not condition():
            if asyncio.get_event_loop().time() - start_time > timeout:
                raise TimeoutError(f"Condition not met within {timeout} seconds")
            await asyncio.sleep(interval)
