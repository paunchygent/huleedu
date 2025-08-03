"""
Database operations integration tests for BatchAuthorMatchesHandler.

Focuses on testing basic CRUD operations, data persistence, and core functionality
with real PostgreSQL without Kafka or Redis dependencies.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.nlp_events import (
    BatchAuthorMatchesSuggestedV1,
    EssayMatchResult,
    StudentMatchSuggestion,
)
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from services.class_management_service.config import Settings
from services.class_management_service.implementations.batch_author_matches_handler import (
    BatchAuthorMatchesHandler,
)
from services.class_management_service.models_db import Base, EssayStudentAssociation, Student


class TestBatchAuthorMatchesDatabaseOperations:
    """Integration tests for basic database operations with real PostgreSQL."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> PostgresContainer:
        """Start PostgreSQL test container."""
        container = PostgresContainer("postgres:15-alpine")
        container.start()
        yield container
        container.stop()

    class DatabaseTestSettings(Settings):
        """Test settings with database URL override."""

        def __init__(self, database_url: str) -> None:
            super().__init__()
            object.__setattr__(self, "_database_url", database_url)

        @property
        def DATABASE_URL(self) -> str:
            return str(object.__getattribute__(self, "_database_url"))

    @pytest.fixture
    def test_settings(self, postgres_container: PostgresContainer) -> Settings:
        """Create test settings with database URL."""
        pg_connection_url = postgres_container.get_connection_url()
        if "+psycopg2://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("postgresql://", "postgresql+asyncpg://")

        return self.DatabaseTestSettings(database_url=pg_connection_url)

    @pytest.fixture
    async def database_engine(self, test_settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
        """Create async database engine with schema."""
        engine = create_async_engine(test_settings.DATABASE_URL)

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
        """Create async session factory."""
        return async_sessionmaker(database_engine, expire_on_commit=False)

    @pytest.fixture(autouse=True)
    async def clean_database(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Clean the database before each test."""
        async with session_factory() as session:
            async with session.begin():
                await session.execute(text("TRUNCATE TABLE essay_student_associations CASCADE"))

    @pytest.fixture
    async def test_students(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> list[Student]:
        """Create test students."""
        # Generate unique suffix to avoid email conflicts
        unique_suffix = str(uuid4())[:8]
        students = [
            Student(
                id=uuid4(),
                first_name="John",
                last_name="Doe",
                email=f"john.doe.{unique_suffix}@ops.test.edu",
                created_by_user_id="test_user",
            ),
            Student(
                id=uuid4(),
                first_name="Jane",
                last_name="Smith",
                email=f"jane.smith.{unique_suffix}@ops.test.edu",
                created_by_user_id="test_user",
            ),
            Student(
                id=uuid4(),
                first_name="Bob",
                last_name="Johnson",
                email=f"bob.johnson.{unique_suffix}@ops.test.edu",
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
        """Mock repository returning test students."""
        repository = AsyncMock()
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
        """Create handler with real session factory."""
        return BatchAuthorMatchesHandler(
            class_repository=mock_class_repository,
            session_factory=session_factory,
        )

    def create_mock_kafka_message(self, envelope: EventEnvelope) -> ConsumerRecord:
        """Create mock Kafka message."""
        kafka_msg = Mock(spec=ConsumerRecord)
        kafka_msg.topic = "test.topic"
        kafka_msg.partition = 0
        kafka_msg.offset = 123
        kafka_msg.value = envelope.model_dump_json().encode("utf-8")
        return kafka_msg

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_successful_association_creation(
        self,
        handler: BatchAuthorMatchesHandler,
        test_students: list[Student],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test successful creation of essay-student associations."""
        # Arrange
        student = test_students[0]
        essay_id = uuid4()

        suggestion = StudentMatchSuggestion(
            student_id=str(student.id),
            student_name=f"{student.first_name} {student.last_name}",
            student_email=student.email or "",
            confidence_score=0.95,
            match_reasons=["name_match", "email_match"],
            extraction_metadata={"extraction_method": "header"},
        )

        batch_event = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            batch_id=str(uuid4()),
            class_id=str(uuid4()),
            match_results=[
                EssayMatchResult(
                    essay_id=str(essay_id),
                    text_storage_id="storage-1",
                    filename="essay1.txt",
                    suggestions=[suggestion],
                    extraction_metadata={"processing_time": 1.5},
                )
            ],
            processing_summary={"total_essays": 1, "matched": 1, "no_match": 0, "errors": 0},
        )

        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            event_timestamp=datetime.now(UTC),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=batch_event,
        )

        kafka_msg = self.create_mock_kafka_message(envelope)

        # Act
        result = await handler.handle(
            msg=kafka_msg,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Assert
        assert result is True

        # Verify association was created correctly
        async with session_factory() as session:
            stmt = select(EssayStudentAssociation).where(
                EssayStudentAssociation.essay_id == essay_id
            )
            result_set = await session.execute(stmt)
            association = result_set.scalar_one_or_none()

            assert association is not None
            assert association.essay_id == essay_id
            assert association.student_id == student.id
            assert association.created_by_user_id == "nlp_service_phase1"
            assert association.created_at is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_associations_creation(
        self,
        handler: BatchAuthorMatchesHandler,
        test_students: list[Student],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test creation of multiple essay-student associations in one batch."""
        # Arrange
        essay_ids = [uuid4(), uuid4(), uuid4()]
        match_results = []

        for i, essay_id in enumerate(essay_ids):
            student = test_students[i % len(test_students)]
            suggestion = StudentMatchSuggestion(
                student_id=str(student.id),
                student_name=f"{student.first_name} {student.last_name}",
                student_email=student.email or "",
                confidence_score=0.95 - (i * 0.1),
                match_reasons=["name_match"],
                extraction_metadata={},
            )

            match_result = EssayMatchResult(
                essay_id=str(essay_id),
                text_storage_id=f"storage-{i}",
                filename=f"essay{i + 1}.txt",
                suggestions=[suggestion],
                extraction_metadata={},
            )
            match_results.append(match_result)

        batch_event = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            batch_id=str(uuid4()),
            class_id=str(uuid4()),
            match_results=match_results,
            processing_summary={"total_essays": 3, "matched": 3, "no_match": 0, "errors": 0},
        )

        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            event_timestamp=datetime.now(UTC),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=batch_event,
        )

        kafka_msg = self.create_mock_kafka_message(envelope)

        # Act
        result = await handler.handle(
            msg=kafka_msg,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Assert
        assert result is True

        # Verify all associations were created
        async with session_factory() as session:
            count_stmt = select(func.count(EssayStudentAssociation.id))
            count_result = await session.execute(count_stmt)
            count = count_result.scalar()
            assert count == 3

            # Verify specific associations
            for essay_id in essay_ids:
                association_stmt = select(EssayStudentAssociation).where(
                    EssayStudentAssociation.essay_id == essay_id
                )
                association_result = await session.execute(association_stmt)
                association = association_result.scalar_one_or_none()
                assert association is not None
                assert association.created_by_user_id == "nlp_service_phase1"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_empty_batch_handling(
        self,
        handler: BatchAuthorMatchesHandler,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test handling of empty batch with no match results."""
        # Arrange
        batch_event = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            batch_id=str(uuid4()),
            class_id=str(uuid4()),
            match_results=[],  # Empty results
            processing_summary={"total_essays": 0, "matched": 0, "no_match": 0, "errors": 0},
        )

        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            event_timestamp=datetime.now(UTC),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=batch_event,
        )

        kafka_msg = self.create_mock_kafka_message(envelope)

        # Act
        result = await handler.handle(
            msg=kafka_msg,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Assert
        assert result is True

        # Verify no associations were created
        async with session_factory() as session:
            stmt = select(func.count(EssayStudentAssociation.id))
            result_set = await session.execute(stmt)
            count = result_set.scalar()
            assert count == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_essays_without_suggestions_skipped(
        self,
        handler: BatchAuthorMatchesHandler,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test that essays without suggestions are skipped gracefully."""
        # Arrange
        batch_event = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            batch_id=str(uuid4()),
            class_id=str(uuid4()),
            match_results=[
                EssayMatchResult(
                    essay_id=str(uuid4()),
                    text_storage_id="storage-1",
                    filename="essay1.txt",
                    suggestions=[],  # No suggestions
                    no_match_reason="No student names found",
                    extraction_metadata={},
                )
            ],
            processing_summary={"total_essays": 1, "matched": 0, "no_match": 1, "errors": 0},
        )

        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            event_timestamp=datetime.now(UTC),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=batch_event,
        )

        kafka_msg = self.create_mock_kafka_message(envelope)

        # Act
        result = await handler.handle(
            msg=kafka_msg,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Assert
        assert result is True

        # Verify no associations were created
        async with session_factory() as session:
            stmt = select(func.count(EssayStudentAssociation.id))
            result_set = await session.execute(stmt)
            count = result_set.scalar()
            assert count == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_highest_confidence_match_stored_only(
        self,
        handler: BatchAuthorMatchesHandler,
        test_students: list[Student],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test that only the highest confidence match is stored per essay (Phase 1 behavior)."""
        # Arrange - Create essay with multiple suggestions
        essay_id = uuid4()
        suggestions = [
            StudentMatchSuggestion(
                student_id=str(test_students[0].id),
                student_name="John Doe",
                student_email="john@test.edu",
                confidence_score=0.95,  # Highest confidence
                match_reasons=["name_match", "email_match"],
                extraction_metadata={},
            ),
            StudentMatchSuggestion(
                student_id=str(test_students[1].id),
                student_name="Jane Smith",
                student_email="jane@test.edu",
                confidence_score=0.80,  # Lower confidence
                match_reasons=["name_match"],
                extraction_metadata={},
            ),
        ]

        batch_event = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            batch_id=str(uuid4()),
            class_id=str(uuid4()),
            match_results=[
                EssayMatchResult(
                    essay_id=str(essay_id),
                    text_storage_id="storage-1",
                    filename="essay1.txt",
                    suggestions=suggestions,  # Multiple suggestions
                    extraction_metadata={},
                )
            ],
            processing_summary={"total_essays": 1, "matched": 1, "no_match": 0, "errors": 0},
        )

        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            event_timestamp=datetime.now(UTC),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=batch_event,
        )

        kafka_msg = self.create_mock_kafka_message(envelope)

        # Act
        result = await handler.handle(
            msg=kafka_msg,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Assert
        assert result is True

        # Verify only one association was created (highest confidence)
        async with session_factory() as session:
            stmt = select(EssayStudentAssociation).where(
                EssayStudentAssociation.essay_id == essay_id
            )
            result_set = await session.execute(stmt)
            association = result_set.scalar_one_or_none()

            assert association is not None
            assert association.student_id == test_students[0].id  # Highest confidence student

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_association_data_persistence(
        self,
        handler: BatchAuthorMatchesHandler,
        test_students: list[Student],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test that association data persists correctly across transactions."""
        # Arrange
        student = test_students[0]
        essay_id = uuid4()

        suggestion = StudentMatchSuggestion(
            student_id=str(student.id),
            student_name=f"{student.first_name} {student.last_name}",
            student_email=student.email or "",
            confidence_score=0.95,
            match_reasons=["name_match"],
            extraction_metadata={},
        )

        batch_event = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            batch_id=str(uuid4()),
            class_id=str(uuid4()),
            match_results=[
                EssayMatchResult(
                    essay_id=str(essay_id),
                    text_storage_id="storage-1",
                    filename="essay1.txt",
                    suggestions=[suggestion],
                    extraction_metadata={},
                )
            ],
            processing_summary={"total_essays": 1, "matched": 1, "no_match": 0, "errors": 0},
        )

        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            event_timestamp=datetime.now(UTC),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=batch_event,
        )

        kafka_msg = self.create_mock_kafka_message(envelope)

        # Act
        result = await handler.handle(
            msg=kafka_msg,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        assert result is True

        # Verify data persists in new session (different transaction)
        async with session_factory() as new_session:
            stmt = select(EssayStudentAssociation).where(
                EssayStudentAssociation.essay_id == essay_id
            )
            result_set = await new_session.execute(stmt)
            association = result_set.scalar_one_or_none()

            assert association is not None
            assert association.essay_id == essay_id
            assert association.student_id == student.id
            assert association.created_by_user_id == "nlp_service_phase1"
            assert association.created_at is not None

            # Verify relationship to student exists
            await new_session.refresh(association, ["student"])
            assert association.student is not None
            assert association.student.first_name == student.first_name
            assert association.student.last_name == student.last_name
