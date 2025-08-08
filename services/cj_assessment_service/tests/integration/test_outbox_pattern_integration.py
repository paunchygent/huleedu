"""
Integration tests for CJ Assessment Service transactional outbox pattern.

Tests the complete outbox workflow including event storage, relay worker processing,
and reliability guarantees. Uses real database with testcontainer-based architecture.
"""

from __future__ import annotations

from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4
import asyncio

import pytest
from common_core.events.envelope import EventEnvelope
from common_core.events.cj_assessment_events import CJAssessmentCompletedV1, CJAssessmentFailedV1
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from huleedu_service_libs.outbox.models import EventOutbox
from huleedu_service_libs.outbox.repository import PostgreSQLOutboxRepository
from huleedu_service_libs.outbox import OutboxProvider
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.event_publisher_impl import CJEventPublisherImpl
from services.cj_assessment_service.implementations.outbox_manager import OutboxManager
from huleedu_service_libs.outbox import EventRelayWorker, OutboxProvider
from huleedu_service_libs.outbox.relay import OutboxSettings
from huleedu_service_libs.redis_client import RedisClient
from services.cj_assessment_service.protocols import CJEventPublisherProtocol
from huleedu_service_libs.outbox.protocols import OutboxRepositoryProtocol


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
        from services.cj_assessment_service.implementations.outbox_manager import OutboxManager
        return OutboxManager(outbox_repository, redis_client, settings)

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self,
        outbox_manager: OutboxManager,
        settings: Settings,
    ) -> CJEventPublisherProtocol:
        """Provide event publisher."""
        return CJEventPublisherImpl(outbox_manager, settings)

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
class TestOutboxPatternIntegration:
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
    async def cleanup_database(self, postgres_engine: AsyncEngine) -> AsyncGenerator[None, None]:
        """Clean outbox table before and after each test to prevent contamination."""
        # Clean before test
        async with postgres_engine.begin() as conn:
            await conn.execute(delete(EventOutbox))
        
        yield
        
        # Clean after test
        async with postgres_engine.begin() as conn:
            await conn.execute(delete(EventOutbox))

    @pytest.fixture
    def test_settings(self) -> Settings:
        """Test settings."""
        settings = Mock(spec=Settings)
        settings.SERVICE_NAME = "cj_assessment_service"
        settings.CJ_ASSESSMENT_COMPLETED_TOPIC = "processing.cj.assessment.completed.v1"
        settings.CJ_ASSESSMENT_FAILED_TOPIC = "processing.cj.assessment.failed.v1"
        settings.KAFKA_BOOTSTRAP_SERVERS = "kafka:9092"
        settings.REDIS_URL = "redis://localhost:6379"
        return settings

    @pytest.fixture
    def mock_kafka_bus(self) -> AsyncMock:
        """Mock Kafka bus with tracking."""
        mock = AsyncMock()
        mock.published_events = []

        async def track_publish(topic: str, envelope: Any, key: str | None = None) -> None:
            mock.published_events.append({
                "topic": topic,
                "envelope": envelope,
                "key": key,
            })

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
    def cj_batch_id(self) -> UUID:
        """Test CJ batch ID."""
        return uuid4()

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
        # Include OutboxProvider from shared library, with test provider overriding specific components
        container = make_async_container(OutboxProvider(), test_provider)
        try:
            yield container
        finally:
            await container.close()

    async def test_assessment_completed_outbox_write(
        self,
        postgres_engine: AsyncEngine,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
        correlation_id: UUID,
        cj_batch_id: UUID,
    ) -> None:
        """Test that CJAssessmentCompletedV1 events are stored in outbox."""
        async with self.create_test_container(
            postgres_engine, mock_kafka_bus, mock_redis_client, test_settings
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(CJEventPublisherProtocol)
                session = await request_container.get(AsyncSession)

                # Create test event data
                from common_core.event_enums import ProcessingEvent
                from common_core.metadata_models import SystemProcessingMetadata
                from common_core.status_enums import BatchStatus, ProcessingStage
                
                system_metadata = SystemProcessingMetadata(
                    entity_id=str(cj_batch_id),
                    entity_type="batch",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    processing_stage=ProcessingStage.COMPLETED,
                    event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
                )
                
                event_data = CJAssessmentCompletedV1(
                    event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
                    entity_id=str(cj_batch_id),
                    entity_type="batch",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    status=BatchStatus.COMPLETED_SUCCESSFULLY,
                    system_metadata=system_metadata,
                    cj_assessment_job_id="cj-job-integ-001",
                    rankings=[
                        {"els_essay_id": "essay-001", "rank": 1, "score": 0.95},
                        {"els_essay_id": "essay-002", "rank": 2, "score": 0.88},
                    ],
                )

                # Create envelope as would be done by event_processor
                envelope: EventEnvelope = EventEnvelope(
                    event_type="processing.cj.assessment.completed.v1",
                    source_service="cj_assessment_service",
                    correlation_id=correlation_id,
                    data=event_data,
                )

                # Publish event
                await event_publisher.publish_assessment_completed(envelope, correlation_id)

                # Verify event is stored in outbox
                stmt = select(EventOutbox).where(
                    EventOutbox.aggregate_id == str(cj_batch_id),
                    EventOutbox.aggregate_type == "cj_batch",
                    EventOutbox.event_type == "processing.cj.assessment.completed.v1",
                )

                result = await session.execute(stmt)
                outbox_event = result.scalar_one()

                assert outbox_event is not None
                assert outbox_event.aggregate_id == str(cj_batch_id)
                assert outbox_event.aggregate_type == "cj_batch"
                assert outbox_event.event_type == "processing.cj.assessment.completed.v1"
                assert outbox_event.topic == "processing.cj.assessment.completed.v1"
                assert outbox_event.event_key == str(cj_batch_id)
                assert outbox_event.published_at is None  # Not yet published
                assert outbox_event.event_data is not None  # Should contain the event envelope

    async def test_assessment_failed_outbox_write(
        self,
        postgres_engine: AsyncEngine,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
        correlation_id: UUID,
        cj_batch_id: UUID,
    ) -> None:
        """Test that CJAssessmentFailedV1 events are stored in outbox."""
        async with self.create_test_container(
            postgres_engine, mock_kafka_bus, mock_redis_client, test_settings
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(CJEventPublisherProtocol)
                session = await request_container.get(AsyncSession)

                # Create test event data
                from common_core.event_enums import ProcessingEvent
                from common_core.metadata_models import SystemProcessingMetadata
                from common_core.status_enums import BatchStatus, ProcessingStage
                
                system_metadata = SystemProcessingMetadata(
                    entity_id=str(cj_batch_id),
                    entity_type="batch",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    processing_stage=ProcessingStage.FAILED,
                    event=ProcessingEvent.CJ_ASSESSMENT_FAILED.value,
                    error_info={
                        "error": "LLM provider timeout",
                        "timeout_seconds": 60,
                        "provider": "openai",
                        "batch_size": 10,
                    },
                )

                event_data = CJAssessmentFailedV1(
                    event_name=ProcessingEvent.CJ_ASSESSMENT_FAILED,
                    entity_id=str(cj_batch_id),
                    entity_type="batch",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    status=BatchStatus.FAILED_CRITICALLY,
                    system_metadata=system_metadata,
                    cj_assessment_job_id="cj-job-integ-fail",
                )

                # Create envelope
                envelope: EventEnvelope = EventEnvelope(
                    event_type="processing.cj.assessment.failed.v1",
                    source_service="cj_assessment_service",
                    correlation_id=correlation_id,
                    data=event_data,
                )

                # Publish event
                await event_publisher.publish_assessment_failed(envelope, correlation_id)

                # Verify event is stored in outbox
                stmt = select(EventOutbox).where(
                    EventOutbox.aggregate_id == str(cj_batch_id),
                    EventOutbox.aggregate_type == "cj_batch",
                    EventOutbox.event_type == "processing.cj.assessment.failed.v1",
                )

                result = await session.execute(stmt)
                outbox_event = result.scalar_one()

                assert outbox_event is not None
                assert outbox_event.aggregate_id == str(cj_batch_id)
                assert outbox_event.topic == "processing.cj.assessment.failed.v1"
                assert outbox_event.published_at is None

                # Verify Redis notification was sent
                mock_redis_client.lpush.assert_called_with("outbox:wake:cj_assessment_service", "1")

    async def test_relay_worker_processes_outbox_events(
        self,
        postgres_engine: AsyncEngine,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
        correlation_id: UUID,
        cj_batch_id: UUID,
    ) -> None:
        """Test that EventRelayWorker processes events from outbox to Kafka."""
        async with self.create_test_container(
            postgres_engine, mock_kafka_bus, mock_redis_client, test_settings
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(CJEventPublisherProtocol)
                relay_worker = await request_container.get(EventRelayWorker)
                session = await request_container.get(AsyncSession)

                # Store event in outbox
                from common_core.event_enums import ProcessingEvent
                from common_core.metadata_models import SystemProcessingMetadata
                from common_core.status_enums import BatchStatus, ProcessingStage
                
                system_metadata = SystemProcessingMetadata(
                    entity_id=str(cj_batch_id),
                    entity_type="batch",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    processing_stage=ProcessingStage.COMPLETED,
                    event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
                )
                
                event_data = CJAssessmentCompletedV1(
                    event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
                    entity_id=str(cj_batch_id),
                    entity_type="batch",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    status=BatchStatus.COMPLETED_SUCCESSFULLY,
                    system_metadata=system_metadata,
                    cj_assessment_job_id="cj-job-relay",
                    rankings=[
                        {"els_essay_id": "essay-relay", "rank": 1, "score": 0.85}
                    ],
                )

                envelope: EventEnvelope = EventEnvelope(
                    event_type="processing.cj.assessment.completed.v1",
                    source_service="cj_assessment_service",
                    correlation_id=correlation_id,
                    data=event_data,
                )

                await event_publisher.publish_assessment_completed(envelope, correlation_id)

                # Verify event stored in outbox before processing
                stmt = select(EventOutbox).where(EventOutbox.published_at.is_(None))
                result = await session.execute(stmt)
                unpublished_events = result.scalars().all()
                assert len(unpublished_events) == 1

                # Start relay worker and process events
                await relay_worker.start()

                try:
                    # Wait for relay worker to process the event
                    await self.wait_for_condition(
                        lambda: len(mock_kafka_bus.published_events) > 0,
                        timeout=3.0,
                    )

                    # Verify Kafka publication
                    assert len(mock_kafka_bus.published_events) == 1
                    published_event = mock_kafka_bus.published_events[0]
                    assert published_event["topic"] == "processing.cj.assessment.completed.v1"
                    assert published_event["key"] == str(cj_batch_id)

                    # Verify event marked as published in outbox
                    await session.refresh(unpublished_events[0])
                    assert unpublished_events[0].published_at is not None

                finally:
                    await relay_worker.stop()

    async def test_outbox_transactional_consistency(
        self,
        postgres_engine: AsyncEngine,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
        correlation_id: UUID,
        cj_batch_id: UUID,
    ) -> None:
        """Test that events are stored atomically with business data."""
        async with self.create_test_container(
            postgres_engine, mock_kafka_bus, mock_redis_client, test_settings
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(CJEventPublisherProtocol)
                session = await request_container.get(AsyncSession)

                # Start transaction
                async with session.begin():
                    # Create event
                    from common_core.event_enums import ProcessingEvent
                    from common_core.metadata_models import SystemProcessingMetadata
                    from common_core.status_enums import BatchStatus, ProcessingStage
                    
                    system_metadata = SystemProcessingMetadata(
                        entity_id=str(cj_batch_id),
                        entity_type="batch",
                        parent_id=None,
                        timestamp=datetime.now(timezone.utc),
                        processing_stage=ProcessingStage.COMPLETED,
                        event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
                    )
                    
                    event_data = CJAssessmentCompletedV1(
                        event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
                        entity_id=str(cj_batch_id),
                        entity_type="batch",
                        parent_id=None,
                        timestamp=datetime.now(timezone.utc),
                        status=BatchStatus.COMPLETED_SUCCESSFULLY,
                        system_metadata=system_metadata,
                        cj_assessment_job_id="cj-job-tx",
                        rankings=[],
                    )

                    envelope: EventEnvelope = EventEnvelope(
                        event_type="processing.cj.assessment.completed.v1",
                        source_service="cj_assessment_service",
                        correlation_id=correlation_id,
                        data=event_data,
                    )

                    # Publish within transaction
                    await event_publisher.publish_assessment_completed(envelope, correlation_id)

                    # Transaction commits here

                # Verify event was committed
                stmt = select(EventOutbox).where(
                    EventOutbox.aggregate_id == str(cj_batch_id)
                )
                result = await session.execute(stmt)
                outbox_event = result.scalar_one_or_none()

                assert outbox_event is not None
                assert outbox_event.aggregate_type == "cj_batch"

    async def test_multiple_events_batch_processing(
        self,
        postgres_engine: AsyncEngine,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
        correlation_id: UUID,
    ) -> None:
        """Test processing multiple events in a batch."""
        async with self.create_test_container(
            postgres_engine, mock_kafka_bus, mock_redis_client, test_settings
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(CJEventPublisherProtocol)
                relay_worker = await request_container.get(EventRelayWorker)
                session = await request_container.get(AsyncSession)

                # Create multiple events
                from common_core.event_enums import ProcessingEvent
                from common_core.metadata_models import SystemProcessingMetadata
                from common_core.status_enums import BatchStatus, ProcessingStage
                
                for i in range(5):
                    batch_id = uuid4()
                    
                    system_metadata = SystemProcessingMetadata(
                        entity_id=str(batch_id),
                        entity_type="batch",
                        parent_id=None,
                        timestamp=datetime.now(timezone.utc),
                        processing_stage=ProcessingStage.COMPLETED,
                        event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
                    )
                    
                    event_data = CJAssessmentCompletedV1(
                        event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
                        entity_id=str(batch_id),
                        entity_type="batch",
                        parent_id=None,
                        timestamp=datetime.now(timezone.utc),
                        status=BatchStatus.COMPLETED_SUCCESSFULLY,
                        system_metadata=system_metadata,
                        cj_assessment_job_id=f"cj-job-multi-{i}",
                        rankings=[
                            {"els_essay_id": f"essay-{i}", "rank": 1, "score": 0.80 + (i * 0.01)}
                        ],
                    )

                    envelope: EventEnvelope = EventEnvelope(
                        event_type="processing.cj.assessment.completed.v1",
                        source_service="cj_assessment_service",
                        correlation_id=correlation_id,
                        data=event_data,
                    )

                    await event_publisher.publish_assessment_completed(envelope, correlation_id)

                # Verify all events stored
                stmt = select(EventOutbox).where(EventOutbox.published_at.is_(None))
                result = await session.execute(stmt)
                unpublished_events = result.scalars().all()
                assert len(unpublished_events) == 5

                # Start relay worker and process events
                await relay_worker.start()

                try:
                    # Wait for relay worker to process all events
                    await self.wait_for_condition(
                        lambda: len(mock_kafka_bus.published_events) >= 5,
                        timeout=5.0,
                    )

                    # Verify all processed
                    assert len(mock_kafka_bus.published_events) == 5

                    # Verify all marked as published
                    for event in unpublished_events:
                        await session.refresh(event)
                        assert event.published_at is not None

                finally:
                    await relay_worker.stop()

    async def test_event_with_custom_partition_key(
        self,
        postgres_engine: AsyncEngine,
        mock_kafka_bus: AsyncMock,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
        correlation_id: UUID,
        cj_batch_id: UUID,
    ) -> None:
        """Test event with custom partition key in metadata."""
        async with self.create_test_container(
            postgres_engine, mock_kafka_bus, mock_redis_client, test_settings
        ) as container:
            async with container() as request_container:
                event_publisher = await request_container.get(CJEventPublisherProtocol)
                relay_worker = await request_container.get(EventRelayWorker)
                session = await request_container.get(AsyncSession)

                # Create event with custom metadata
                from common_core.event_enums import ProcessingEvent
                from common_core.metadata_models import SystemProcessingMetadata
                from common_core.status_enums import BatchStatus, ProcessingStage
                
                system_metadata = SystemProcessingMetadata(
                    entity_id=str(cj_batch_id),
                    entity_type="batch",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    processing_stage=ProcessingStage.COMPLETED,
                    event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
                )
                
                event_data = CJAssessmentCompletedV1(
                    event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
                    entity_id=str(cj_batch_id),
                    entity_type="batch",
                    parent_id=None,
                    timestamp=datetime.now(timezone.utc),
                    status=BatchStatus.COMPLETED_SUCCESSFULLY,
                    system_metadata=system_metadata,
                    cj_assessment_job_id="cj-job-partition-key",
                    rankings=[],
                )

                envelope: EventEnvelope = EventEnvelope(
                    event_type="processing.cj.assessment.completed.v1",
                    source_service="cj_assessment_service",
                    correlation_id=correlation_id,
                    data=event_data,
                    metadata={"partition_key": "custom-partition-key"},
                )

                # Publish event
                await event_publisher.publish_assessment_completed(envelope, correlation_id)

                # Verify custom partition key stored
                stmt = select(EventOutbox).where(
                    EventOutbox.aggregate_id == str(cj_batch_id)
                )
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