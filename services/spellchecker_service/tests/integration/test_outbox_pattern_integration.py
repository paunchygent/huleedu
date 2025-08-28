"""
Integration tests for Spellchecker Service transactional outbox pattern.

Tests the complete outbox workflow including event storage, relay worker processing,
and reliability guarantees using in-memory SQLite for simplicity and speed.
"""

from __future__ import annotations

import asyncio
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Callable
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.metadata_models import StorageReferenceMetadata, SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from huleedu_service_libs.outbox import EventRelayWorker, OutboxProvider
from huleedu_service_libs.outbox.manager import OutboxManager
from huleedu_service_libs.outbox.models import EventOutbox
from huleedu_service_libs.outbox.protocols import OutboxRepositoryProtocol
from huleedu_service_libs.outbox.relay import OutboxSettings
from huleedu_service_libs.outbox.repository import PostgreSQLOutboxRepository
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from services.spellchecker_service.config import Settings
from services.spellchecker_service.implementations.event_publisher_impl import (
    DefaultSpellcheckEventPublisher,
)
from services.spellchecker_service.protocols import SpellcheckEventPublisherProtocol


@pytest.fixture
async def temp_database_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create temporary SQLite database engine for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_spellchecker.db"
        database_url = f"sqlite+aiosqlite:///{db_path}"

        engine = create_async_engine(database_url, echo=False)

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(EventOutbox.metadata.create_all)

        try:
            yield engine
        finally:
            await engine.dispose()


class OutboxIntegrationTestProvider(Provider):
    """DI provider for integration tests."""

    def __init__(
        self,
        engine: AsyncEngine,
        kafka_bus: AsyncMock,
        redis_client: AsyncMock,
        settings: Settings,
    ) -> None:
        super().__init__()
        self._engine = engine
        self._kafka_bus = kafka_bus
        self._redis_client = redis_client
        self._settings = settings

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide test settings."""
        return self._settings

    @provide(scope=Scope.APP)
    def provide_database_engine(self) -> AsyncEngine:
        """Provide database engine."""
        return self._engine

    @provide(scope=Scope.REQUEST)
    async def provide_session(self, engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
        """Provide database session."""
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            yield session

    @provide(scope=Scope.APP)
    def provide_outbox_repository(
        self, engine: AsyncEngine, settings: Settings
    ) -> OutboxRepositoryProtocol:
        """Provide outbox repository."""
        return PostgreSQLOutboxRepository(
            engine=engine,
            service_name=settings.SERVICE_NAME,
            enable_metrics=False,
        )

    @provide(scope=Scope.APP)
    def provide_service_name(self, settings: Settings) -> str:
        """Provide service name for OutboxProvider dependency."""
        return settings.SERVICE_NAME

    @provide(scope=Scope.APP)
    def provide_redis_client(self) -> AtomicRedisClientProtocol:
        """Provide mock Redis client."""
        return self._redis_client

    @provide(scope=Scope.APP)
    def provide_kafka_bus(self) -> Any:
        """Provide mock Kafka bus."""
        return self._kafka_bus

    @provide(scope=Scope.APP)
    def provide_outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> OutboxManager:
        """Provide outbox manager for transactional event publishing."""
        return OutboxManager(outbox_repository, redis_client, settings.SERVICE_NAME)

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self,
        outbox_manager: OutboxManager,
        settings: Settings,
    ) -> SpellcheckEventPublisherProtocol:
        """Provide event publisher."""
        return DefaultSpellcheckEventPublisher(
            source_service_name="spell-checker-service",
            outbox_manager=outbox_manager,
        )

    @provide(scope=Scope.APP)
    def provide_outbox_settings(self) -> OutboxSettings:
        """Provide test outbox settings."""
        return OutboxSettings(
            poll_interval_seconds=0.1,
            batch_size=10,
            max_retries=3,
            enable_metrics=False,
        )

    @provide(scope=Scope.APP)
    def provide_relay_worker(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        kafka_bus: Any,
        redis_client: Any,
        settings: OutboxSettings,
        service_name: str,
    ) -> EventRelayWorker:
        """Provide relay worker."""
        return EventRelayWorker(
            outbox_repository=outbox_repository,
            kafka_bus=kafka_bus,
            settings=settings,
            service_name=service_name,
            redis_client=redis_client,
        )


@pytest.mark.integration
class TestSpellcheckerOutboxPatternIntegration:
    """Integration tests for the transactional outbox pattern."""

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

    @pytest.fixture(autouse=True)
    async def cleanup_database(
        self, temp_database_engine: AsyncEngine
    ) -> AsyncGenerator[None, None]:
        """Clean outbox table before and after each test to prevent contamination."""
        # Clean before test
        async with temp_database_engine.begin() as conn:
            await conn.execute(delete(EventOutbox))

        yield

        # Clean after test
        async with temp_database_engine.begin() as conn:
            await conn.execute(delete(EventOutbox))

    @pytest.fixture
    def test_settings(self) -> Settings:
        """Test settings."""
        settings = Mock(spec=Settings)
        settings.SERVICE_NAME = "spell-checker-service"
        return settings

    @pytest.fixture
    def mock_kafka_bus(self) -> AsyncMock:
        """Mock Kafka bus with tracking."""
        mock = AsyncMock()
        mock.published_events = []

        async def track_publish(
            topic: str, envelope: Any, key: str | None = None, headers: dict[str, str] | None = None
        ) -> None:
            mock.published_events.append(
                {
                    "topic": topic,
                    "envelope": envelope,
                    "key": key,
                    "headers": headers,
                }
            )

        mock.publish.side_effect = track_publish
        return mock

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Mock Redis client."""
        return AsyncMock()

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Test correlation ID."""
        return uuid4()

    @pytest.fixture
    def essay_id(self) -> str:
        """Test essay ID."""
        return f"essay-{uuid4()}"

    @asynccontextmanager
    async def create_test_container(
        self,
        engine: AsyncEngine,
        kafka_bus: AsyncMock,
        redis_client: AsyncMock,
        settings: Settings,
    ) -> AsyncGenerator[AsyncContainer, None]:
        """Create test DI container."""
        test_provider = OutboxIntegrationTestProvider(
            engine=engine,
            kafka_bus=kafka_bus,
            redis_client=redis_client,
            settings=settings,
        )
        # Include OutboxProvider from shared library, with test provider overriding
        # specific components
        container = make_async_container(OutboxProvider(), test_provider)
        try:
            yield container
        finally:
            await container.close()

    async def test_spellcheck_result_outbox_write(
        self,
        temp_database_engine: AsyncEngine,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
        correlation_id: UUID,
        essay_id: str,
    ) -> None:
        """Test that SpellcheckResultDataV1 events are stored in outbox."""
        async with self.create_test_container(
            temp_database_engine, mock_kafka_bus, mock_redis_client, test_settings
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(SpellcheckEventPublisherProtocol)
                session = await request_container.get(AsyncSession)

                # Create test event data
                system_metadata = SystemProcessingMetadata(
                    entity_id=essay_id,
                    entity_type="essay",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    processing_stage=ProcessingStage.COMPLETED,
                    event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
                )

                storage_metadata = StorageReferenceMetadata(
                    storage_id="corrected-text-123",
                    content_type="text/plain",
                    file_name=f"{essay_id}_corrected.txt",
                )

                event_data = SpellcheckResultDataV1(
                    event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
                    entity_id=essay_id,
                    entity_type="essay",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    status=EssayStatus.SPELLCHECKED_SUCCESS,
                    system_metadata=system_metadata,
                    original_text_storage_id="original-text-123",
                    storage_metadata=storage_metadata,
                    corrections_made=5,
                )

                # Publish event
                await event_publisher.publish_spellcheck_result(event_data, correlation_id)

                # Verify TWO events are stored in outbox (thin + rich dual pattern)
                stmt = select(EventOutbox).where(
                    EventOutbox.aggregate_id == essay_id,
                    EventOutbox.aggregate_type == "spellcheck_job",
                )

                result = await session.execute(stmt)
                outbox_events = result.scalars().all()

                # Should have exactly 2 events: thin and rich
                assert len(outbox_events) == 2

                # Sort events by topic to ensure consistent ordering
                thin_topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)
                rich_topic = topic_name(ProcessingEvent.SPELLCHECK_RESULTS)

                thin_event = next((e for e in outbox_events if e.event_type == thin_topic), None)
                rich_event = next((e for e in outbox_events if e.event_type == rich_topic), None)

                # Verify thin event (for ELS/BCS state management)
                assert thin_event is not None
                assert thin_event.aggregate_id == essay_id
                assert thin_event.aggregate_type == "spellcheck_job"
                assert thin_event.event_type == thin_topic
                assert thin_event.topic == thin_topic
                assert thin_event.event_key == essay_id
                assert thin_event.published_at is None
                assert thin_event.event_data is not None

                # Verify rich event (for RAS business data)
                assert rich_event is not None
                assert rich_event.aggregate_id == essay_id
                assert rich_event.aggregate_type == "spellcheck_job"
                assert rich_event.event_type == rich_topic
                assert rich_event.topic == rich_topic
                assert rich_event.event_key == essay_id
                assert rich_event.published_at is None
                assert rich_event.event_data is not None

                # Verify Redis notification was sent
                mock_redis_client.lpush.assert_called_with(
                    "outbox:wake:spell-checker-service", "wake"
                )

    async def test_relay_worker_processes_outbox_events(
        self,
        temp_database_engine: AsyncEngine,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
        correlation_id: UUID,
        essay_id: str,
    ) -> None:
        """Test that EventRelayWorker processes events from outbox to Kafka."""
        async with self.create_test_container(
            temp_database_engine, mock_kafka_bus, mock_redis_client, test_settings
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(SpellcheckEventPublisherProtocol)
                relay_worker = await request_container.get(EventRelayWorker)
                session = await request_container.get(AsyncSession)

                # Store event in outbox
                system_metadata = SystemProcessingMetadata(
                    entity_id=essay_id,
                    entity_type="essay",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    processing_stage=ProcessingStage.COMPLETED,
                    event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
                )

                event_data = SpellcheckResultDataV1(
                    event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
                    entity_id=essay_id,
                    entity_type="essay",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    status=EssayStatus.SPELLCHECKED_SUCCESS,
                    system_metadata=system_metadata,
                    original_text_storage_id="original-relay-123",
                    storage_metadata=None,
                    corrections_made=2,
                )

                await event_publisher.publish_spellcheck_result(event_data, correlation_id)

                # Verify TWO events stored in outbox before processing (dual pattern)
                stmt = select(EventOutbox).where(EventOutbox.published_at.is_(None))
                result = await session.execute(stmt)
                unpublished_events = result.scalars().all()
                assert len(unpublished_events) == 2

                # Start relay worker and process events
                await relay_worker.start()

                try:
                    # Wait for relay worker to process both events
                    await self.wait_for_condition(
                        lambda: len(mock_kafka_bus.published_events) >= 2,
                        timeout=3.0,
                    )

                    # Verify Kafka publication of both events
                    assert len(mock_kafka_bus.published_events) == 2

                    # Get expected topics using enums
                    thin_topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)
                    rich_topic = topic_name(ProcessingEvent.SPELLCHECK_RESULTS)

                    published_topics = [event["topic"] for event in mock_kafka_bus.published_events]
                    assert thin_topic in published_topics
                    assert rich_topic in published_topics

                    # Verify event keys are correct for both events
                    for published_event in mock_kafka_bus.published_events:
                        assert published_event["key"] == essay_id

                    # Verify both events marked as published in outbox
                    for event in unpublished_events:
                        await session.refresh(event)
                        assert event.published_at is not None

                finally:
                    await relay_worker.stop()

    async def test_outbox_transactional_consistency(
        self,
        temp_database_engine: AsyncEngine,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
        correlation_id: UUID,
        essay_id: str,
    ) -> None:
        """Test that events are stored atomically with business data."""
        async with self.create_test_container(
            temp_database_engine, mock_kafka_bus, mock_redis_client, test_settings
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(SpellcheckEventPublisherProtocol)
                session = await request_container.get(AsyncSession)

                # Start transaction
                async with session.begin():
                    # Create event
                    system_metadata = SystemProcessingMetadata(
                        entity_id=essay_id,
                        entity_type="essay",
                        parent_id=None,
                        timestamp=datetime.now(timezone.utc),
                        processing_stage=ProcessingStage.COMPLETED,
                        event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
                    )

                    event_data = SpellcheckResultDataV1(
                        event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
                        entity_id=essay_id,
                        entity_type="essay",
                        parent_id=None,
                        timestamp=datetime.now(timezone.utc),
                        status=EssayStatus.SPELLCHECKED_SUCCESS,
                        system_metadata=system_metadata,
                        original_text_storage_id="original-tx-123",
                        storage_metadata=None,
                        corrections_made=3,
                    )

                    # Publish within transaction
                    await event_publisher.publish_spellcheck_result(event_data, correlation_id)

                    # Transaction commits here

                # Verify BOTH events were committed (dual pattern)
                stmt = select(EventOutbox).where(EventOutbox.aggregate_id == essay_id)
                result = await session.execute(stmt)
                outbox_events = result.scalars().all()

                assert len(outbox_events) == 2

                # Verify both events have correct aggregate type
                for event in outbox_events:
                    assert event.aggregate_type == "spellcheck_job"
                    assert event.aggregate_id == essay_id

                # Verify we have both thin and rich event types using enums
                thin_topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)
                rich_topic = topic_name(ProcessingEvent.SPELLCHECK_RESULTS)

                event_types = [event.event_type for event in outbox_events]
                assert thin_topic in event_types
                assert rich_topic in event_types

    async def test_multiple_events_batch_processing(
        self,
        temp_database_engine: AsyncEngine,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
        correlation_id: UUID,
    ) -> None:
        """Test processing multiple events in a batch."""
        async with self.create_test_container(
            temp_database_engine, mock_kafka_bus, mock_redis_client, test_settings
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(SpellcheckEventPublisherProtocol)
                relay_worker = await request_container.get(EventRelayWorker)
                session = await request_container.get(AsyncSession)

                # Create multiple events
                essay_ids = [f"essay-{uuid4()}" for _ in range(3)]

                for i, essay_id in enumerate(essay_ids):
                    system_metadata = SystemProcessingMetadata(
                        entity_id=essay_id,
                        entity_type="essay",
                        parent_id=None,
                        timestamp=datetime.now(timezone.utc),
                        processing_stage=ProcessingStage.COMPLETED,
                        event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
                    )

                    event_data = SpellcheckResultDataV1(
                        event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
                        entity_id=essay_id,
                        entity_type="essay",
                        parent_id=None,
                        timestamp=datetime.now(timezone.utc),
                        status=EssayStatus.SPELLCHECKED_SUCCESS,
                        system_metadata=system_metadata,
                        original_text_storage_id=f"original-multi-{i}",
                        storage_metadata=None,
                        corrections_made=i + 1,
                    )

                    await event_publisher.publish_spellcheck_result(event_data, correlation_id)

                # Verify all events stored (3 essays × 2 events each = 6 total)
                stmt = select(EventOutbox).where(EventOutbox.published_at.is_(None))
                result = await session.execute(stmt)
                unpublished_events = result.scalars().all()
                assert len(unpublished_events) == 6  # 3 essays with dual events each

                # Start relay worker and process events
                await relay_worker.start()

                try:
                    # Wait for relay worker to process all events
                    await self.wait_for_condition(
                        lambda: len(mock_kafka_bus.published_events) >= 6,
                        timeout=5.0,
                    )

                    # Verify all processed (3 essays × 2 events each = 6 total)
                    assert len(mock_kafka_bus.published_events) == 6

                    # Verify all marked as published
                    for event in unpublished_events:
                        await session.refresh(event)
                        assert event.published_at is not None

                finally:
                    await relay_worker.stop()

    async def test_event_with_custom_partition_key(
        self,
        temp_database_engine: AsyncEngine,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
        correlation_id: UUID,
        essay_id: str,
    ) -> None:
        """Test event with custom partition key in metadata."""
        async with self.create_test_container(
            temp_database_engine, mock_kafka_bus, mock_redis_client, test_settings
        ) as container:
            async with container() as request_container:
                outbox_manager = await request_container.get(OutboxManager)
                relay_worker = await request_container.get(EventRelayWorker)
                session = await request_container.get(AsyncSession)

                # Create event with custom metadata
                system_metadata = SystemProcessingMetadata(
                    entity_id=essay_id,
                    entity_type="essay",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    processing_stage=ProcessingStage.COMPLETED,
                    event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
                )

                event_data = SpellcheckResultDataV1(
                    event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
                    entity_id=essay_id,
                    entity_type="essay",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    status=EssayStatus.SPELLCHECKED_SUCCESS,
                    system_metadata=system_metadata,
                    original_text_storage_id="original-partition-key",
                    storage_metadata=None,
                    corrections_made=1,
                )

                envelope: EventEnvelope = EventEnvelope(
                    event_type="huleedu.essay.spellcheck.completed.v1",
                    source_service="spell-checker-service",
                    correlation_id=correlation_id,
                    data=event_data,
                    metadata={"partition_key": "custom-partition-key"},
                )

                # Publish event directly via outbox manager to test custom key
                await outbox_manager.publish_to_outbox(
                    aggregate_type="spellcheck_job",
                    aggregate_id=essay_id,
                    event_type="huleedu.essay.spellcheck.completed.v1",
                    event_data=envelope,
                    topic="huleedu.essay.spellcheck.completed.v1",
                )

                # Verify custom partition key stored
                stmt = select(EventOutbox).where(EventOutbox.aggregate_id == essay_id)
                result = await session.execute(stmt)
                outbox_event = result.scalar_one()

                assert outbox_event.event_key == "custom-partition-key"

                # Start relay worker and process events
                await relay_worker.start()

                try:
                    # Wait for relay worker to process the event
                    await self.wait_for_condition(
                        lambda: len(mock_kafka_bus.published_events) > 0,
                        timeout=3.0,
                    )

                    # Process and verify Kafka publication uses custom key
                    assert len(mock_kafka_bus.published_events) == 1
                    assert mock_kafka_bus.published_events[0]["key"] == "custom-partition-key"

                finally:
                    await relay_worker.stop()
