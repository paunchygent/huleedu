"""
Kafka integration tests for BatchAuthorMatchesHandler.

Focuses on testing real Kafka message flow, Redis idempotency, and event processor routing
with minimal database operations. Database-specific tests are in separate files.

Tests:
- Real Kafka producer/consumer message flow
- Redis-based idempotency behavior
- Event processor routing and handler selection
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, ConsumerRecord
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.events.nlp_events import (
    BatchAuthorMatchesSuggestedV1,
    EssayMatchResult,
    StudentMatchSuggestion,
)
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.kafka import KafkaContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from services.class_management_service.config import Settings
from services.class_management_service.event_processor import process_single_message
from services.class_management_service.implementations.batch_author_matches_handler import (
    BatchAuthorMatchesHandler,
)
from services.class_management_service.models_db import Base, EssayStudentAssociation, Student
from services.class_management_service.protocols import CommandHandlerProtocol


class TestBatchAuthorMatchesKafkaIntegration:
    """Integration tests focusing on Kafka message flow, Redis idempotency, and event routing."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> Generator[PostgresContainer, None, None]:
        """Start PostgreSQL test container for integration tests."""
        with PostgresContainer("postgres:15-alpine") as container:
            yield container

    @pytest.fixture(scope="class")
    def kafka_container(self) -> Generator[KafkaContainer, None, None]:
        """Start Kafka test container for integration tests."""
        with KafkaContainer("confluentinc/cp-kafka:7.4.0") as container:
            yield container

    @pytest.fixture(scope="class")
    def redis_container(self) -> Generator[RedisContainer, None, None]:
        """Start Redis test container for idempotency testing."""
        with RedisContainer("redis:7-alpine") as container:
            yield container

    class IntegrationTestSettings(Settings):
        """Test settings that override database and service URLs."""

        def __init__(self, database_url: str, kafka_bootstrap_servers: str, redis_url: str) -> None:
            super().__init__()
            object.__setattr__(self, "_database_url", database_url)
            self.KAFKA_BOOTSTRAP_SERVERS = kafka_bootstrap_servers
            self.REDIS_URL = redis_url

        @property
        def DATABASE_URL(self) -> str:
            """Override to return test database URL."""
            return str(object.__getattribute__(self, "_database_url"))

    @pytest.fixture
    def test_settings(
        self,
        postgres_container: PostgresContainer,
        kafka_container: KafkaContainer,
        redis_container: RedisContainer,
    ) -> Settings:
        """Create test settings pointing to test containers."""
        # Get PostgreSQL connection URL with asyncpg driver
        pg_connection_url = postgres_container.get_connection_url()
        if "+psycopg2://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("postgresql://", "postgresql+asyncpg://")

        # Get Kafka bootstrap servers
        kafka_bootstrap_servers = kafka_container.get_bootstrap_server()

        # Get Redis connection URL
        redis_connection_url = (
            f"redis://{redis_container.get_container_host_ip()}:"
            f"{redis_container.get_exposed_port(6379)}"
        )

        return self.IntegrationTestSettings(
            database_url=pg_connection_url,
            kafka_bootstrap_servers=kafka_bootstrap_servers,
            redis_url=redis_connection_url,
        )

    @pytest.fixture
    async def database_engine(self, test_settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
        """Create async database engine with test database."""
        engine = create_async_engine(test_settings.DATABASE_URL)

        # Initialize database schema
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        try:
            yield engine
        finally:
            await engine.dispose()

    @pytest.fixture
    async def session_factory(
        self, database_engine: AsyncEngine
    ) -> async_sessionmaker[AsyncSession]:
        """Create async session factory for tests."""
        return async_sessionmaker(database_engine, expire_on_commit=False)

    @pytest.fixture(autouse=True)
    async def clean_database(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Clean the database before each test for isolation."""
        async with session_factory() as session:
            async with session.begin():
                await session.execute(text("TRUNCATE TABLE essay_student_associations CASCADE"))

    @pytest.fixture
    async def redis_client(
        self, test_settings: Settings
    ) -> AsyncGenerator[AtomicRedisClientProtocol, None]:
        """Create real Redis client for idempotency testing."""
        client = RedisClient(client_id="test-cms", redis_url=test_settings.REDIS_URL)
        await client.start()

        try:
            # Clear any existing data
            await client.client.flushdb()
            yield client
        finally:
            await client.stop()

    @pytest.fixture
    async def test_students(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> list[Student]:
        """Create test students in the database."""
        # Generate unique suffix to avoid email conflicts
        unique_suffix = str(uuid4())[:8]
        students = [
            Student(
                id=uuid4(),
                first_name="John",
                last_name="Doe",
                email=f"john.doe.{unique_suffix}@kafka.test.edu",
                created_by_user_id="test_user",
            ),
            Student(
                id=uuid4(),
                first_name="Jane",
                last_name="Smith",
                email=f"jane.smith.{unique_suffix}@kafka.test.edu",
                created_by_user_id="test_user",
            ),
            Student(
                id=uuid4(),
                first_name="Bob",
                last_name="Johnson",
                email=f"bob.johnson.{unique_suffix}@kafka.test.edu",
                created_by_user_id="test_user",
            ),
        ]

        async with session_factory() as session:
            async with session.begin():
                for student in students:
                    session.add(student)

        return students

    @pytest.fixture
    def mock_class_repository(self, test_students: list[Student]) -> AsyncMock:
        """Mock class repository that returns test students."""
        repository = AsyncMock()

        # Create lookup map for students
        student_map = {student.id: student for student in test_students}

        async def get_student_by_id(student_id: UUID) -> Student | None:
            return student_map.get(student_id)

        repository.get_student_by_id.side_effect = get_student_by_id
        return repository

    @pytest.fixture
    def handler(
        self,
        mock_class_repository: AsyncMock,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> BatchAuthorMatchesHandler:
        """Create handler with real session factory and mock repository."""
        return BatchAuthorMatchesHandler(
            class_repository=mock_class_repository,
            session_factory=session_factory,
        )

    @pytest.fixture
    async def kafka_producer(
        self, test_settings: Settings
    ) -> AsyncGenerator[AIOKafkaProducer, None]:
        """Create Kafka producer for sending test events."""
        producer = AIOKafkaProducer(
            bootstrap_servers=test_settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await producer.start()

        try:
            yield producer
        finally:
            await producer.stop()

    @pytest.fixture
    async def kafka_consumer(
        self, test_settings: Settings
    ) -> AsyncGenerator[AIOKafkaConsumer, None]:
        """Create Kafka consumer for receiving test events."""
        consumer = AIOKafkaConsumer(
            "huleedu.nlp.batch.author.matches.suggested.v1",
            bootstrap_servers=test_settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="test-consumer-group",
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        await consumer.start()

        try:
            yield consumer
        finally:
            await consumer.stop()

    def create_batch_event(
        self, test_students: list[Student], essay_count: int = 2
    ) -> BatchAuthorMatchesSuggestedV1:
        """Create a batch author matches suggested event with test data."""
        match_results = []

        for i in range(essay_count):
            # Cycle through available students
            student = test_students[i % len(test_students)]

            suggestion = StudentMatchSuggestion(
                student_id=str(student.id),
                student_name=f"{student.first_name} {student.last_name}",
                student_email=student.email or "",
                confidence_score=0.95 - (i * 0.1),  # Decreasing confidence
                match_reasons=["name_match", "email_match"],
                extraction_metadata={
                    "extraction_method": "header",
                    "matched_name": f"{student.first_name} {student.last_name}",
                },
            )

            match_result = EssayMatchResult(
                essay_id=str(uuid4()),
                text_storage_id=f"storage-{i}",
                filename=f"essay{i + 1}.txt",
                suggestions=[suggestion],
                extraction_metadata={"processing_time": 1.5 + i},
            )
            match_results.append(match_result)

        return BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            batch_id=str(uuid4()),
            class_id=str(uuid4()),
            match_results=match_results,
            processing_summary={
                "total_essays": essay_count,
                "matched": essay_count,
                "no_match": 0,
                "errors": 0,
            },
            processing_metadata={"nlp_model": "phase1_matcher_v1.0"},
        )

    def create_event_envelope(
        self, event_data: BatchAuthorMatchesSuggestedV1, correlation_id: UUID | None = None
    ) -> EventEnvelope[BatchAuthorMatchesSuggestedV1]:
        """Create an event envelope for the batch event."""
        return EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type="huleedu.nlp.batch.author.matches.suggested.v1",
            event_timestamp=datetime.now(UTC),
            source_service="nlp_service",
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

    def create_kafka_message(
        self, envelope: EventEnvelope, topic: str, key: str | None = None
    ) -> ConsumerRecord:
        """Create a Kafka ConsumerRecord from an envelope."""
        message_value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        kafka_msg = Mock(spec=ConsumerRecord)
        kafka_msg.topic = topic
        kafka_msg.partition = 0
        kafka_msg.offset = 123
        kafka_msg.key = key.encode("utf-8") if key else None
        kafka_msg.value = message_value
        return kafka_msg

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_kafka_event_processing_flow(
        self,
        handler: BatchAuthorMatchesHandler,
        test_students: list[Student],
        session_factory: async_sessionmaker[AsyncSession],
        kafka_producer: AIOKafkaProducer,
        kafka_consumer: AIOKafkaConsumer,
    ) -> None:
        """Test complete Kafka event processing flow with real infrastructure."""
        # Arrange
        correlation_id = uuid4()
        batch_event = self.create_batch_event(test_students, essay_count=3)
        envelope = self.create_event_envelope(batch_event, correlation_id)

        # Act - Send event through real Kafka
        await kafka_producer.send_and_wait(
            "huleedu.nlp.batch.author.matches.suggested.v1",
            envelope.model_dump(mode="json"),
            key=batch_event.batch_id.encode("utf-8"),  # Kafka key must be bytes
        )

        # Consume the message from Kafka with timeout
        consumer_msg = None
        try:
            # Wait for message with timeout (10 seconds)
            async with asyncio.timeout(10.0):
                async for msg in kafka_consumer:
                    consumer_msg = msg
                    break
        except asyncio.TimeoutError:
            pytest.fail("Timeout waiting for Kafka message")

        assert consumer_msg is not None

        # Process the message using the handler (simulate real event processor flow)
        # In real flow, the envelope comes from parsing the Kafka message
        raw_message = consumer_msg.value.decode("utf-8")
        parsed_envelope = EventEnvelope.model_validate_json(raw_message)
        
        mock_http_session = AsyncMock()
        result = await handler.handle(
            msg=consumer_msg,
            envelope=parsed_envelope,  # Use parsed envelope, not original
            http_session=mock_http_session,
            correlation_id=correlation_id,
            span=None,
        )

        # Assert - Verify processing succeeded
        assert result is True

        # Verify database state
        async with session_factory() as session:
            # Check that associations were created
            stmt = select(
                EssayStudentAssociation.essay_id,
                EssayStudentAssociation.student_id,
                EssayStudentAssociation.created_by_user_id,
            )
            result_set = await session.execute(stmt)
            associations = result_set.fetchall()

            # Should have 3 associations (one per essay)
            assert len(associations) == 3

            # Verify each association has correct data
            for association in associations:
                assert association[2] == "nlp_service_phase1"  # created_by_user_id
                assert association[0] is not None  # essay_id
                assert association[1] is not None  # student_id

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_idempotency_with_real_redis(
        self,
        handler: BatchAuthorMatchesHandler,
        test_students: list[Student],
        session_factory: async_sessionmaker[AsyncSession],
        redis_client: AtomicRedisClientProtocol,
    ) -> None:
        """Test idempotency behavior with real Redis infrastructure."""
        # Arrange
        correlation_id = uuid4()
        batch_event = self.create_batch_event(test_students, essay_count=2)
        envelope = self.create_event_envelope(batch_event, correlation_id)
        kafka_msg = self.create_kafka_message(
            envelope, "huleedu.nlp.batch.author.matches.suggested.v1", batch_event.batch_id
        )

        mock_http_session = AsyncMock()

        # Act - Process same message twice
        result1 = await handler.handle(
            msg=kafka_msg,
            envelope=envelope,
            http_session=mock_http_session,
            correlation_id=correlation_id,
            span=None,
        )

        result2 = await handler.handle(
            msg=kafka_msg,
            envelope=envelope,
            http_session=mock_http_session,
            correlation_id=correlation_id,
            span=None,
        )

        # Assert - Both should succeed
        assert result1 is True
        assert result2 is True

        # Verify only one set of associations was created
        async with session_factory() as session:
            stmt = select(func.count(EssayStudentAssociation.id))
            result_set = await session.execute(stmt)
            count = result_set.scalar()
            assert count == 2  # Only 2 associations, not 4

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_event_processor_routing_integration(
        self,
        test_students: list[Student],
        session_factory: async_sessionmaker[AsyncSession],
        mock_class_repository: AsyncMock,
    ) -> None:
        """Test event processor routing with real handler integration."""
        # Arrange
        handler = BatchAuthorMatchesHandler(
            class_repository=mock_class_repository,
            session_factory=session_factory,
        )

        command_handlers: dict[str, CommandHandlerProtocol] = {
            "batch_author_matches": handler,
        }

        correlation_id = uuid4()
        batch_event = self.create_batch_event(test_students, essay_count=1)
        envelope = self.create_event_envelope(batch_event, correlation_id)
        kafka_msg = self.create_kafka_message(
            envelope, "huleedu.nlp.batch.author.matches.suggested.v1"
        )

        mock_http_session = AsyncMock()

        # Act - Process through event processor (simulates real flow)
        result = await process_single_message(
            msg=kafka_msg,
            command_handlers=command_handlers,
            http_session=mock_http_session,
            tracer=None,
        )

        # Assert
        assert result is True

        # Verify database operations occurred
        async with session_factory() as session:
            stmt = select(func.count(EssayStudentAssociation.id))
            result_set = await session.execute(stmt)
            count = result_set.scalar()
            assert count == 1
