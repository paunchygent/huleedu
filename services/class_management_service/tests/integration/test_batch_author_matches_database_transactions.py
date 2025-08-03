"""
Database transaction integration tests for BatchAuthorMatchesHandler.

Focuses on testing transaction behavior, rollback scenarios, and concurrent operations
with real PostgreSQL without Kafka or Redis dependencies.
"""

from __future__ import annotations

import asyncio
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


class TestBatchAuthorMatchesDatabaseTransactions:
    """Integration tests for database transactions with real PostgreSQL."""

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
                email=f"john.doe.{unique_suffix}@tx.test.edu",
                created_by_user_id="test_user",
            ),
            Student(
                id=uuid4(),
                first_name="Jane",
                last_name="Smith",
                email=f"jane.smith.{unique_suffix}@tx.test.edu",
                created_by_user_id="test_user",
            ),
            Student(
                id=uuid4(),
                first_name="Bob",
                last_name="Johnson",
                email=f"bob.johnson.{unique_suffix}@tx.test.edu",
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

    def create_batch_event(
        self, test_students: list[Student], essay_count: int = 2
    ) -> BatchAuthorMatchesSuggestedV1:
        """Create test batch event."""
        match_results = []

        for i in range(essay_count):
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
                essay_id=str(uuid4()),
                text_storage_id=f"storage-{i}",
                filename=f"essay{i + 1}.txt",
                suggestions=[suggestion],
                extraction_metadata={},
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
    async def test_partial_batch_failure_transaction_behavior(
        self,
        handler: BatchAuthorMatchesHandler,
        test_students: list[Student],
        session_factory: async_sessionmaker[AsyncSession],
        mock_class_repository: AsyncMock,
    ) -> None:
        """Test transaction behavior with partial batch failures."""
        # Arrange - Create event with multiple essays where one will fail
        batch_event = self.create_batch_event(test_students, essay_count=3)
        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            event_timestamp=datetime.now(UTC),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=batch_event,
        )
        kafka_msg = self.create_mock_kafka_message(envelope)

        # Make the second student lookup fail
        call_count = 0

        def failing_get_student_by_id(student_id: UUID) -> Student | None:
            nonlocal call_count
            student_map = {student.id: student for student in test_students}
            call_count += 1

            if call_count == 2:
                raise Exception("Database error for student lookup")
            return student_map.get(student_id)

        mock_class_repository.get_student_by_id.side_effect = failing_get_student_by_id

        # Act
        result = await handler.handle(
            msg=kafka_msg,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Assert - Should succeed (partial success acceptable)
        assert result is True

        # Verify database state - should have associations for successful essays
        async with session_factory() as session:
            stmt = select(func.count(EssayStudentAssociation.id))
            result_set = await session.execute(stmt)
            count = result_set.scalar()
            # Should have 2 associations (first and third essays succeeded)
            assert count == 2

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_concurrent_batch_processing(
        self,
        handler: BatchAuthorMatchesHandler,
        test_students: list[Student],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test concurrent processing with real PostgreSQL."""
        # Arrange - Create multiple different batch events
        events_count = 10
        tasks = []

        for i in range(events_count):
            batch_event = self.create_batch_event(test_students, essay_count=2)
            envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
                event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
                event_timestamp=datetime.now(UTC),
                source_service="nlp_service",
                correlation_id=uuid4(),
                data=batch_event,
            )
            kafka_msg = self.create_mock_kafka_message(envelope)

            task = asyncio.create_task(
                handler.handle(
                    msg=kafka_msg,
                    envelope=envelope,
                    http_session=AsyncMock(),
                    correlation_id=uuid4(),
                    span=None,
                )
            )
            tasks.append(task)

        # Act - Process all events concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert - All should succeed
        successful_results = [r for r in results if r is True]
        failed_results = [r for r in results if isinstance(r, Exception)]

        assert len(successful_results) == events_count
        assert len(failed_results) == 0

        # Verify database state
        async with session_factory() as session:
            stmt = select(func.count(EssayStudentAssociation.id))
            result_set = await session.execute(stmt)
            count = result_set.scalar()
            # Each event has 2 essays, so expect 20 associations
            assert count == events_count * 2

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_transaction_isolation_levels(
        self,
        handler: BatchAuthorMatchesHandler,
        test_students: list[Student],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test transaction isolation with concurrent reads and writes."""
        # Arrange - Create two events with same essay IDs to test isolation
        essay_id = uuid4()

        # First event
        batch_event1 = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            batch_id=str(uuid4()),
            class_id=str(uuid4()),
            match_results=[
                EssayMatchResult(
                    essay_id=str(essay_id),
                    text_storage_id="storage-1",
                    filename="essay1.txt",
                    suggestions=[
                        StudentMatchSuggestion(
                            student_id=str(test_students[0].id),
                            student_name="John Doe",
                            student_email="john@test.edu",
                            confidence_score=0.95,
                            match_reasons=["name_match"],
                            extraction_metadata={},
                        )
                    ],
                    extraction_metadata={},
                )
            ],
            processing_summary={"total_essays": 1, "matched": 1, "no_match": 0, "errors": 0},
        )

        # Second event with same essay ID but different student
        batch_event2 = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            batch_id=str(uuid4()),
            class_id=str(uuid4()),
            match_results=[
                EssayMatchResult(
                    essay_id=str(essay_id),  # Same essay ID
                    text_storage_id="storage-1",
                    filename="essay1.txt",
                    suggestions=[
                        StudentMatchSuggestion(
                            student_id=str(test_students[1].id),  # Different student
                            student_name="Jane Smith",
                            student_email="jane@test.edu",
                            confidence_score=0.90,
                            match_reasons=["name_match"],
                            extraction_metadata={},
                        )
                    ],
                    extraction_metadata={},
                )
            ],
            processing_summary={"total_essays": 1, "matched": 1, "no_match": 0, "errors": 0},
        )

        envelope1 = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            event_timestamp=datetime.now(UTC),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=batch_event1,
        )

        envelope2 = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            event_timestamp=datetime.now(UTC),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=batch_event2,
        )

        kafka_msg1 = self.create_mock_kafka_message(envelope1)
        kafka_msg2 = self.create_mock_kafka_message(envelope2)

        # Act - Process both events concurrently
        task1 = asyncio.create_task(
            handler.handle(
                msg=kafka_msg1,
                envelope=envelope1,
                http_session=AsyncMock(),
                correlation_id=uuid4(),
                span=None,
            )
        )

        task2 = asyncio.create_task(
            handler.handle(
                msg=kafka_msg2,
                envelope=envelope2,
                http_session=AsyncMock(),
                correlation_id=uuid4(),
                span=None,
            )
        )

        results = await asyncio.gather(task1, task2, return_exceptions=True)

        # Assert - Both should succeed
        assert results[0] is True
        assert results[1] is True

        # Verify only one association exists (first one wins)
        async with session_factory() as session:
            stmt = select(
                EssayStudentAssociation.student_id,
            ).where(EssayStudentAssociation.essay_id == essay_id)
            result_set = await session.execute(stmt)
            associations = result_set.fetchall()

            # Should have exactly one association
            assert len(associations) == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_transaction_commit_rollback_behavior(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        test_students: list[Student],
    ) -> None:
        """Test explicit transaction commit and rollback behavior."""
        essay_id = uuid4()
        student = test_students[0]

        # Test successful commit
        async with session_factory() as session:
            async with session.begin():
                association = EssayStudentAssociation(
                    essay_id=essay_id,
                    student_id=student.id,
                    created_by_user_id="test_commit",
                )
                session.add(association)
                # Transaction commits automatically at end of context

        # Verify association was committed
        async with session_factory() as session:
            stmt = select(EssayStudentAssociation).where(
                EssayStudentAssociation.essay_id == essay_id
            )
            result_set = await session.execute(stmt)
            committed_association = result_set.scalar_one_or_none()
            assert committed_association is not None
            assert committed_association.created_by_user_id == "test_commit"

        # Test rollback behavior
        rollback_essay_id = uuid4()
        try:
            async with session_factory() as session:
                async with session.begin():
                    association = EssayStudentAssociation(
                        essay_id=rollback_essay_id,
                        student_id=student.id,
                        created_by_user_id="test_rollback",
                    )
                    session.add(association)
                    # Force an exception to trigger rollback
                    raise Exception("Intentional rollback")
        except Exception:
            pass  # Expected exception

        # Verify association was rolled back
        async with session_factory() as session:
            stmt = select(EssayStudentAssociation).where(
                EssayStudentAssociation.essay_id == rollback_essay_id
            )
            result_set = await session.execute(stmt)
            rollback_association = result_set.scalar_one_or_none()
            assert rollback_association is None
