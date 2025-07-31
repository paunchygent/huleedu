"""
Integration tests for Batch Orchestrator Service transactional outbox pattern.

Tests the complete outbox workflow including event storage, relay worker processing,
and reliability guarantees during various failure scenarios.

IMPROVEMENTS:
- Proper resource cleanup with try/finally blocks
- Event-based synchronization instead of sleep-based timing
- Consistent session management
- Better test isolation
- Renamed Provider class to avoid pytest warnings
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from common_core.batch_service_models import (
    BatchServiceNLPInitiateCommandDataV1,
    BatchServiceSpellcheckInitiateCommandDataV1,
)
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EssayProcessingInputRefV1
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from huleedu_service_libs.outbox import EventRelayWorker, OutboxRepositoryProtocol
from huleedu_service_libs.outbox.models import EventOutbox
from huleedu_service_libs.outbox.relay import OutboxSettings
from huleedu_service_libs.outbox.repository import PostgreSQLOutboxRepository
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.implementations.event_publisher_impl import (
    DefaultBatchEventPublisherImpl,
)
from services.batch_orchestrator_service.implementations.outbox_manager import OutboxManager
from services.batch_orchestrator_service.protocols import BatchEventPublisherProtocol


class OutboxTestProvider(Provider):
    """DI provider for outbox integration tests."""

    def __init__(self, engine: AsyncEngine, kafka_publisher: AsyncMock, settings: Settings):
        super().__init__()
        self._engine = engine
        self._kafka_publisher = kafka_publisher
        self._settings = settings
        self._redis_client = AsyncMock(spec=AtomicRedisClientProtocol)
        self._redis_client.lpush = AsyncMock(return_value=None)

    @provide(scope=Scope.APP)
    async def provide_engine(self) -> AsyncEngine:
        """Provide test database engine."""
        return self._engine

    @provide(scope=Scope.APP)
    def provide_kafka_publisher(self) -> KafkaPublisherProtocol:
        """Provide mock Kafka publisher."""
        return self._kafka_publisher

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Any:
        """Provide test settings (mock object with custom attributes)."""
        return self._settings

    @provide(scope=Scope.APP)
    def provide_outbox_repository(self, engine: AsyncEngine) -> OutboxRepositoryProtocol:
        """Provide outbox repository."""
        return PostgreSQLOutboxRepository(engine)

    @provide(scope=Scope.APP)
    def provide_outbox_settings(self) -> OutboxSettings:
        """Provide outbox settings."""
        return OutboxSettings(
            poll_interval_seconds=5.0,
            batch_size=100,
            max_retries=3,
        )

    @provide(scope=Scope.APP)
    def provide_service_name(self) -> str:
        """Provide service name for outbox metadata."""
        return self._settings.SERVICE_NAME

    @provide(scope=Scope.APP)
    def provide_redis_client(self) -> AtomicRedisClientProtocol:
        """Provide mock Redis client."""
        return self._redis_client

    @provide(scope=Scope.APP)
    def provide_outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Any,
    ) -> OutboxManager:
        """Provide outbox manager for TRUE OUTBOX PATTERN."""
        return OutboxManager(outbox_repository, redis_client, settings)

    @provide(scope=Scope.REQUEST)
    def provide_event_publisher(
        self,
        outbox_manager: OutboxManager,
        settings: Any,
    ) -> BatchEventPublisherProtocol:
        """Provide event publisher with outbox support."""
        return DefaultBatchEventPublisherImpl(outbox_manager, settings)

    @provide(scope=Scope.APP)
    def provide_event_relay_worker(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        kafka_publisher: KafkaPublisherProtocol,
        settings: Any,
    ) -> EventRelayWorker:
        """Provide event relay worker with configurable settings."""
        # Use settings from fixture, allowing tests to customize
        outbox_settings = OutboxSettings(
            poll_interval_seconds=settings.OUTBOX_POLL_INTERVAL_SECONDS,
            batch_size=settings.OUTBOX_BATCH_SIZE,
            max_retries=settings.OUTBOX_MAX_RETRIES,
        )

        return EventRelayWorker(
            outbox_repository=outbox_repository,
            kafka_bus=kafka_publisher,
            settings=outbox_settings,
            service_name=settings.SERVICE_NAME,
        )


@pytest.mark.asyncio
class TestOutboxPatternIntegration:
    """Integration tests for the transactional outbox pattern."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> PostgresContainer:
        """Start PostgreSQL test container for integration tests."""
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
        # Convert to asyncpg URL
        connection_url = connection_url.replace("+psycopg2://", "+asyncpg://")
        connection_url = connection_url.replace("postgresql://", "postgresql+asyncpg://")

        engine = create_async_engine(connection_url, echo=False)

        try:
            # Create outbox table
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
        """Create session factory for tests."""
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
    def make_test_settings(self) -> Callable[[float, int], Any]:
        """Factory for creating test settings with custom values."""

        def _make_settings(poll_interval: float = 0.1, batch_size: int = 5) -> Any:
            settings = MagicMock()
            settings.SERVICE_NAME = "batch-orchestrator-service"
            settings.OUTBOX_POLL_INTERVAL_SECONDS = poll_interval
            settings.OUTBOX_BATCH_SIZE = batch_size
            settings.OUTBOX_MAX_RETRIES = 5
            return settings

        return _make_settings

    @asynccontextmanager
    async def create_test_container(
        self,
        engine: AsyncEngine,
        kafka_publisher: AsyncMock,
        settings: Settings,
    ) -> AsyncGenerator[AsyncContainer, None]:
        """Create DI container with proper cleanup."""
        container = make_async_container(OutboxTestProvider(engine, kafka_publisher, settings))
        try:
            yield container
        finally:
            # Ensure container resources are cleaned up
            await container.close()

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Generate test correlation ID."""
        return uuid4()

    @pytest.fixture(autouse=True)
    async def clean_outbox_table(self, test_engine: AsyncEngine) -> AsyncGenerator[None, None]:
        """Clean the outbox table before and after each test."""
        # Clean before test
        async with test_engine.begin() as conn:
            await conn.execute(delete(EventOutbox))

        yield

        # Clean after test (for good measure)
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

    async def test_batch_size_limits_improved(
        self,
        test_engine: AsyncEngine,
        mock_kafka_publisher: AsyncMock,
        make_test_settings: Callable,
        correlation_id: UUID,
    ) -> None:
        """Test relay worker batch processing with event-based synchronization."""
        # Create settings with specific batch size
        settings = make_test_settings(poll_interval=0.05, batch_size=5)

        async with self.create_test_container(
            test_engine, mock_kafka_publisher, settings
        ) as container:
            # Store 15 events
            async with container() as request_container:
                event_publisher = await request_container.get(BatchEventPublisherProtocol)

                for i in range(15):
                    command_data = BatchServiceSpellcheckInitiateCommandDataV1(
                        event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
                        entity_id=f"batch-{i}",
                        entity_type="batch",
                        essays_to_process=[
                            EssayProcessingInputRefV1(
                                essay_id=f"essay{i}", text_storage_id=f"storage{i}"
                            ),
                        ],
                        language="en",
                    )

                    event_envelope = EventEnvelope[BatchServiceSpellcheckInitiateCommandDataV1](
                        event_type="huleedu.batch.spellcheck.initiate.command.v1",
                        source_service="batch-orchestrator-service",
                        correlation_id=correlation_id,
                        data=command_data,
                    )

                    await event_publisher.publish_batch_event(event_envelope, key=f"batch-{i}")

            # Process with relay worker using event-based waiting
            async with container() as request_container:
                relay_worker = await request_container.get(EventRelayWorker)

                # Start worker
                await relay_worker.start()

                try:
                    # Wait for all events to be processed (relay worker processes continuously)
                    await self.wait_for_condition(
                        lambda: len(mock_kafka_publisher.published_events) >= 15, timeout=2.0
                    )
                    assert len(mock_kafka_publisher.published_events) == 15

                    # Verify all events were published with correct data
                    published_event_ids = {
                        event["envelope"].data["entity_id"]
                        for event in mock_kafka_publisher.published_events
                    }
                    expected_event_ids = {f"batch-{i}" for i in range(15)}
                    assert published_event_ids == expected_event_ids

                finally:
                    # Always stop the worker
                    await relay_worker.stop()

    async def test_transactional_consistency(
        self,
        test_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
        correlation_id: UUID,
    ) -> None:
        """Test that outbox writes are transactional with business operations."""
        outbox_repository = PostgreSQLOutboxRepository(test_engine)

        # Test rollback scenario
        try:
            async with db_session_factory() as session:
                async with session.begin():
                    # Add event to outbox within transaction
                    event_id = await outbox_repository.add_event(
                        aggregate_id="test-rollback",
                        aggregate_type="batch",
                        event_type="test.event",
                        event_data={"test": "data"},
                        topic="test.topic",
                        event_key="test-key",
                        session=session,
                    )

                    # Verify it exists within transaction
                    result = await session.execute(
                        select(EventOutbox).where(EventOutbox.id == event_id)
                    )
                    assert result.scalar_one_or_none() is not None

                    # Force rollback
                    raise Exception("Intentional rollback")
        except Exception as e:
            assert str(e) == "Intentional rollback"

        # Verify event was rolled back
        async with db_session_factory() as session:
            result = await session.execute(
                select(EventOutbox).where(EventOutbox.aggregate_id == "test-rollback")
            )
            assert result.scalar_one_or_none() is None

    async def test_concurrent_workers_with_locking(
        self,
        test_engine: AsyncEngine,
        mock_kafka_publisher: AsyncMock,
        make_test_settings: Callable,
        correlation_id: UUID,
    ) -> None:
        """Test concurrent relay workers don't double-process with proper locking."""
        settings = make_test_settings(poll_interval=0.05, batch_size=10)

        # Create mock that tracks which worker processed each event
        processed_by_worker = {}

        async def track_worker_publish(**kwargs: Any) -> None:
            event_id = kwargs["envelope"].event_id
            task = asyncio.current_task()
            worker_id = task.get_name() if task else "unknown"
            processed_by_worker[event_id] = worker_id
            mock_kafka_publisher.published_events.append(kwargs)

        mock_kafka_publisher.publish.side_effect = track_worker_publish

        async with self.create_test_container(
            test_engine, mock_kafka_publisher, settings
        ) as container:
            # Create test events
            async with container() as request_container:
                event_publisher = await request_container.get(BatchEventPublisherProtocol)

                for i in range(5):
                    command_data = BatchServiceNLPInitiateCommandDataV1(
                        event_name=ProcessingEvent.BATCH_NLP_INITIATE_COMMAND,
                        entity_id=f"concurrent-{i}",
                        entity_type="batch",
                        essays_to_process=[
                            EssayProcessingInputRefV1(
                                essay_id=f"essay{i}", text_storage_id=f"storage{i}"
                            ),
                        ],
                        language="en",
                    )

                    event_envelope = EventEnvelope[BatchServiceNLPInitiateCommandDataV1](
                        event_type="huleedu.batch.nlp.initiate.command.v1",
                        source_service="batch-orchestrator-service",
                        correlation_id=correlation_id,
                        data=command_data,
                    )

                    await event_publisher.publish_batch_event(event_envelope, key=f"concurrent-{i}")

            # Start two workers concurrently
            async with container() as request_container1:
                async with container() as request_container2:
                    worker1 = await request_container1.get(EventRelayWorker)
                    worker2 = await request_container2.get(EventRelayWorker)

                    # Name tasks for tracking
                    task1 = asyncio.create_task(worker1.start(), name="worker1")
                    task2 = asyncio.create_task(worker2.start(), name="worker2")

                    try:
                        # Wait for all events to be processed
                        await self.wait_for_condition(
                            lambda: len(mock_kafka_publisher.published_events) == 5, timeout=2.0
                        )

                        # Verify no double processing
                        assert len(mock_kafka_publisher.published_events) == 5
                        assert len(set(processed_by_worker.keys())) == 5  # All unique events

                    finally:
                        # Stop both workers
                        await worker1.stop()
                        await worker2.stop()
                        task1.cancel()
                        task2.cancel()
                        try:
                            await asyncio.gather(task1, task2)
                        except asyncio.CancelledError:
                            pass
