"""
Integration tests for NLP Service command handlers with TRUE OUTBOX PATTERN.

Tests the complete integration of command handlers with real infrastructure
to verify that student matching commands use the TRUE OUTBOX PATTERN correctly.

Uses real PostgreSQL and Redis infrastructure with testcontainers.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from common_core.events.envelope import EventEnvelope
from common_core.events.essay_lifecycle_events import BatchStudentMatchingRequestedV1
from common_core.events.nlp_events import StudentMatchSuggestion
from common_core.metadata_models import EssayProcessingInputRefV1
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from services.nlp_service.command_handlers.essay_student_matching_handler import (
    EssayStudentMatchingHandler,
)
from services.nlp_service.config import Settings
from services.nlp_service.implementations.outbox_manager import OutboxManager
from services.nlp_service.protocols import (
    NlpEventPublisherProtocol,
)


class MockContentClient:
    """Mock content client for testing."""

    async def fetch_content(
        self,
        storage_id: str,
        http_session: Any,
        correlation_id: UUID,
    ) -> str:
        """Return mock essay content."""
        return f"Mock essay content for storage {storage_id}\\n\\nStudent: Test Student\\nEmail: test@student.edu"


class MockClassManagementClient:
    """Mock class management client for testing."""

    async def get_class_roster(
        self,
        class_id: str,
        http_session: Any,
        correlation_id: UUID,
    ) -> list[dict]:
        """Return mock class roster."""
        return [
            {
                "student_id": "student-1",
                "student_name": "Test Student",
                "email": "test@student.edu",
                "phone": "+1234567890",
            },
            {
                "student_id": "student-2",
                "student_name": "Another Student",
                "email": "another@student.edu",
                "phone": "+0987654321",
            },
        ]


class MockRosterCache:
    """Mock roster cache for testing."""

    def __init__(self) -> None:
        self.cache: dict[str, list[dict]] = {}

    async def get_roster(self, class_id: str) -> list[dict] | None:
        """Get cached roster."""
        return self.cache.get(class_id)

    async def set_roster(
        self,
        class_id: str,
        roster: list[dict],
        ttl_seconds: int = 3600,
    ) -> None:
        """Cache roster."""
        self.cache[class_id] = roster


class MockStudentMatcher:
    """Mock student matcher for testing."""

    async def find_matches(
        self,
        essay_text: str,
        roster: list[dict],
        correlation_id: UUID,
    ) -> list[StudentMatchSuggestion]:
        """Return mock student matches."""
        if "Test Student" in essay_text:
            return [
                StudentMatchSuggestion(
                    student_id="student-1",
                    student_name="Test Student",
                    confidence_score=0.95,
                    match_reasons=["name_match", "email_match"],
                    extracted_identifiers={
                        "name": "Test Student",
                        "email": "test@student.edu",
                    },
                )
            ]
        return []


class TestCommandHandlerOutboxIntegration:
    """Integration tests for command handlers with TRUE OUTBOX PATTERN."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> Generator[PostgresContainer, Any, None]:
        """Start PostgreSQL test container for integration tests."""
        container = PostgresContainer("postgres:15")
        container.start()
        yield container
        container.stop()

    @pytest.fixture(scope="class")
    def redis_container(self) -> Generator[RedisContainer, Any, None]:
        """Start Redis test container for integration tests."""
        container = RedisContainer("redis:7-alpine")
        container.start()
        yield container
        container.stop()

    class IntegrationTestSettings(Settings):
        """Test settings that override database and Redis URLs."""

        def __init__(self, database_url: str, redis_url: str) -> None:
            super().__init__()
            object.__setattr__(self, "_database_url", database_url)
            self.REDIS_URL = redis_url

        @property
        def database_url(self) -> str:
            """Override to return test database URL."""
            return str(object.__getattribute__(self, "_database_url"))

    @pytest.fixture
    def test_settings(
        self, postgres_container: PostgresContainer, redis_container: RedisContainer
    ) -> Settings:
        """Create test settings pointing to test containers."""
        # Get PostgreSQL connection URL with asyncpg driver
        pg_connection_url = postgres_container.get_connection_url()
        if "+psycopg2://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("postgresql://", "postgresql+asyncpg://")

        # Get Redis connection URL
        redis_connection_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"

        return self.IntegrationTestSettings(
            database_url=pg_connection_url, redis_url=redis_connection_url
        )

    @pytest.fixture
    async def redis_client(self, test_settings: Settings) -> AsyncGenerator[Any, None]:
        """Create real Redis client for testing."""
        from huleedu_service_libs.redis_client import RedisClient

        client = RedisClient(client_id="test-nlp", redis_url=test_settings.REDIS_URL)
        await client.start()

        try:
            # Clear any existing data
            await client.client.flushdb()
            yield client
        finally:
            await client.stop()

    @pytest.fixture
    async def outbox_repository(
        self, test_settings: Settings
    ) -> AsyncGenerator[OutboxRepositoryProtocol, None]:
        """Create real outbox repository with PostgreSQL."""
        from huleedu_service_libs.outbox import PostgreSQLOutboxRepository
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(test_settings.database_url)

        # Initialize schema for outbox
        from huleedu_service_libs.outbox.models import EventOutbox
        from sqlalchemy import MetaData

        async with engine.begin() as conn:
            metadata = MetaData()
            await conn.run_sync(metadata.reflect, bind=engine.sync_engine)
            if EventOutbox.__tablename__ not in metadata.tables:
                await conn.run_sync(EventOutbox.metadata.create_all)

        repository = PostgreSQLOutboxRepository(engine)
        yield repository

        # Cleanup
        await engine.dispose()

    @pytest.fixture
    def outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        test_settings: Settings,
    ) -> OutboxManager:
        """Create real outbox manager."""
        return OutboxManager(
            outbox_repository=outbox_repository,
            redis_client=redis_client,
            settings=test_settings,
        )

    @pytest.fixture
    def mock_event_publisher(self, outbox_manager: OutboxManager) -> AsyncMock:
        """Create mock event publisher that uses real outbox manager."""
        from services.nlp_service.implementations.event_publisher_impl import (
            DefaultNlpEventPublisher,
        )

        publisher = DefaultNlpEventPublisher(
            outbox_manager=outbox_manager,
            source_service_name="nlp-service",
            output_topic="huleedu.nlp.batch.author.matches.suggested.v1",
        )
        return publisher

    @pytest.fixture
    def essay_student_matching_handler(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        mock_event_publisher: NlpEventPublisherProtocol,
    ) -> EssayStudentMatchingHandler:
        """Create essay student matching handler with real dependencies."""
        mock_kafka_bus = AsyncMock(spec=KafkaPublisherProtocol)

        return EssayStudentMatchingHandler(
            content_client=MockContentClient(),
            class_management_client=MockClassManagementClient(),
            roster_cache=MockRosterCache(),
            student_matcher=MockStudentMatcher(),
            event_publisher=mock_event_publisher,
            outbox_repository=outbox_repository,
            kafka_bus=mock_kafka_bus,
        )

    @pytest.mark.asyncio
    async def test_essay_student_matching_uses_outbox_integration(
        self,
        essay_student_matching_handler: EssayStudentMatchingHandler,
        outbox_repository: OutboxRepositoryProtocol,
    ) -> None:
        """Test that essay student matching handler uses TRUE OUTBOX PATTERN."""
        # Arrange
        correlation_id = uuid4()

        # Create mock Kafka message and envelope
        mock_msg = Mock()
        mock_msg.topic = "test.topic"
        mock_msg.partition = 0
        mock_msg.offset = 123

        event_data = BatchStudentMatchingRequestedV1(
            batch_id="test-batch-123",
            essays_to_process=[
                EssayProcessingInputRefV1(
                    essay_id="essay-1",
                    text_storage_id="storage-1",
                    student_name="Unknown Student",
                )
            ],
            class_id="test-class-456",
        )

        envelope = EventEnvelope(
            event_type="huleedu.essay.student.matching.requested.v1",
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=event_data,
        )

        # Mock HTTP session
        mock_http_session = AsyncMock()

        # Act
        result = await essay_student_matching_handler.handle(
            msg=mock_msg,
            envelope=envelope,
            http_session=mock_http_session,
            correlation_id=correlation_id,
        )

        # Assert - Handler succeeded
        assert result is True

        # Assert - Event was stored in outbox (TRUE OUTBOX PATTERN)
        # Check that events were added to the outbox repository
        async with outbox_repository.get_connection() as session:
            unpublished_events = await outbox_repository.get_unpublished_events(
                session=session, limit=10
            )

            # Should have at least one event in outbox
            assert len(unpublished_events) >= 1

            # Verify event structure
            event = unpublished_events[0]
            assert event.aggregate_type == "essay"
            assert event.event_type == "batch.author.matches.suggested.v1"
            assert event.topic == "huleedu.nlp.batch.author.matches.suggested.v1"

            # Verify event data contains expected structure
            event_data_dict = event.event_data
            assert "event_type" in event_data_dict
            assert "source_service" in event_data_dict
            assert "correlation_id" in event_data_dict
            assert "data" in event_data_dict

    @pytest.mark.asyncio
    async def test_command_handler_never_uses_direct_kafka(
        self,
        essay_student_matching_handler: EssayStudentMatchingHandler,
    ) -> None:
        """Test that command handler never calls Kafka directly."""
        # Arrange
        correlation_id = uuid4()

        mock_msg = Mock()
        event_data = BatchStudentMatchingRequestedV1(
            batch_id="test-batch-789",
            essays_to_process=[
                EssayProcessingInputRefV1(
                    essay_id="essay-2",
                    text_storage_id="storage-2",
                    student_name="Test Student",
                )
            ],
            class_id="test-class-999",
        )

        envelope = EventEnvelope(
            event_type="huleedu.essay.student.matching.requested.v1",
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=event_data,
        )

        mock_http_session = AsyncMock()

        # Get reference to the kafka_bus to verify it's never called
        kafka_bus = essay_student_matching_handler.kafka_bus

        # Act
        await essay_student_matching_handler.handle(
            msg=mock_msg,
            envelope=envelope,
            http_session=mock_http_session,
            correlation_id=correlation_id,
        )

        # Assert - Kafka bus publish method was NEVER called (TRUE OUTBOX PATTERN)
        kafka_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_outbox_atomic_behavior_with_failure(
        self,
        essay_student_matching_handler: EssayStudentMatchingHandler,
        outbox_repository: OutboxRepositoryProtocol,
    ) -> None:
        """Test that outbox operations are atomic with business logic failures."""
        # Arrange
        correlation_id = uuid4()

        # Mock the student matcher to fail
        essay_student_matching_handler.student_matcher.find_matches = AsyncMock(
            side_effect=Exception("Student matching failed")
        )

        mock_msg = Mock()
        event_data = BatchStudentMatchingRequestedV1(
            batch_id="test-batch-failure",
            essays_to_process=[
                EssayProcessingInputRefV1(
                    essay_id="essay-fail",
                    text_storage_id="storage-fail",
                    student_name="Test Student",
                )
            ],
            class_id="test-class-fail",
        )

        envelope = EventEnvelope(
            event_type="huleedu.essay.student.matching.requested.v1",
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=event_data,
        )

        mock_http_session = AsyncMock()

        # Act & Assert - Handler should fail
        with pytest.raises(Exception, match="Student matching failed"):
            await essay_student_matching_handler.handle(
                msg=mock_msg,
                envelope=envelope,
                http_session=mock_http_session,
                correlation_id=correlation_id,
            )

        # Assert - No events should be in outbox due to failure before publishing
        async with outbox_repository.get_connection() as session:
            unpublished_events = await outbox_repository.get_unpublished_events(
                session=session, limit=10
            )

            # Filter for events from this specific test
            test_events = [
                event
                for event in unpublished_events
                if "test-batch-failure" in str(event.event_data)
            ]

            # Should have no events from failed operation
            assert len(test_events) == 0
