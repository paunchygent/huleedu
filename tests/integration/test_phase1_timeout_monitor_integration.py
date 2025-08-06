"""
Integration tests for AssociationTimeoutMonitor 24-hour timeout behavior.

Tests the timeout monitor's core functionality with real database operations:
- 24-hour timeout trigger with time manipulation
- High confidence auto-confirmation (≥0.7)
- Low confidence UNKNOWN student creation (<0.7)
- Multiple batch isolation and processing
- Cross-service event propagation

Following 070-testing-standards.mdc and 075-test-creation-methodology.mdc
Using testcontainers for authentic database behavior.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from common_core.domain_enums import CourseCode, Language
from common_core.events.envelope import EventEnvelope
from common_core.events.validation_events import (
    StudentAssociationConfirmation,
    StudentAssociationsConfirmedV1,
)
from common_core.status_enums import AssociationValidationMethod
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from services.class_management_service.implementations.association_timeout_monitor import (
    HIGH_CONFIDENCE_THRESHOLD,
    AssociationTimeoutMonitor,
)
from services.class_management_service.models_db import (
    Base,
    Course,
    EssayStudentAssociation,
    Student,
    UserClass,
)


class BatchTestData:
    """Test data container for batch setup."""

    def __init__(
        self,
        batch_id: UUID,
        course: Course,
        user_class: UserClass,
        students: list[Student],
        associations: list[EssayStudentAssociation],
    ):
        self.batch_id = batch_id
        self.course = course
        self.user_class = user_class
        self.students = students
        self.associations = associations


class MockEventPublisher:
    """Mock event publisher that tracks published events for verification."""

    def __init__(self):
        self.published_events: list[StudentAssociationsConfirmedV1] = []
        self.publish_calls: list[dict[str, Any]] = []
        self.class_events: list[EventEnvelope] = []

    async def publish_class_event(self, event_envelope: EventEnvelope) -> None:
        """Mock implementation for ClassEventPublisherProtocol compliance."""
        self.class_events.append(event_envelope)

    async def publish_student_associations_confirmed(
        self,
        batch_id: str,
        class_id: str,
        course_code: CourseCode,
        associations: list[dict[str, Any]],
        timeout_triggered: bool,
        validation_summary: dict[str, int],
        correlation_id: UUID,
    ) -> None:
        """Mock implementation that tracks published events."""
        # Convert dict associations to StudentAssociationConfirmation objects
        # for proper event structure
        association_confirmations = [
            StudentAssociationConfirmation(
                essay_id=assoc["essay_id"],
                student_id=assoc["student_id"],
                confidence_score=assoc["confidence_score"],
                validation_method=AssociationValidationMethod(assoc["validation_method"]),
                validated_by=assoc["validated_by"],
                validated_at=assoc["validated_at"],
            )
            for assoc in associations
        ]

        # Create the event object for verification
        event = StudentAssociationsConfirmedV1(
            batch_id=batch_id,
            class_id=class_id,
            course_code=course_code,
            associations=association_confirmations,
            timeout_triggered=timeout_triggered,
            validation_summary=validation_summary,
        )

        self.published_events.append(event)
        self.publish_calls.append(
            {
                "batch_id": batch_id,
                "class_id": class_id,
                "course_code": course_code,
                "associations": associations,
                "timeout_triggered": timeout_triggered,
                "validation_summary": validation_summary,
                "correlation_id": correlation_id,
            }
        )


class TestTimeoutMonitorIntegration:
    """Integration tests for AssociationTimeoutMonitor with real database."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> PostgresContainer:
        """Start PostgreSQL test container following project patterns."""
        container = PostgresContainer("postgres:15-alpine")
        container.start()
        yield container
        container.stop()

    @pytest.fixture
    def database_url(self, postgres_container: PostgresContainer) -> str:
        """Create asyncpg-compatible database URL from container."""
        pg_connection_url: str = postgres_container.get_connection_url()
        # Convert to asyncpg URL format following project patterns
        if "+psycopg2://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("postgresql://", "postgresql+asyncpg://")
        return pg_connection_url

    @pytest.fixture
    async def engine(self, database_url: str) -> AsyncGenerator[AsyncEngine, None]:
        """Create async engine connected to test database."""
        engine = create_async_engine(database_url, echo=False)

        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        try:
            yield engine
        finally:
            await engine.dispose()

    @pytest.fixture
    async def session_factory(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        """Create session factory for database operations."""
        return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @pytest.fixture
    def mock_event_publisher(self) -> MockEventPublisher:
        """Create mock event publisher for tracking published events."""
        return MockEventPublisher()

    @pytest.fixture(autouse=True)
    async def clean_database(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Clean the database before each test to prevent data contamination."""
        async with session_factory() as session:
            # Delete all data in reverse dependency order
            await session.execute(text("DELETE FROM essay_student_associations"))
            await session.execute(text("DELETE FROM class_student_association"))
            await session.execute(text("DELETE FROM students"))
            await session.execute(text("DELETE FROM classes"))
            await session.execute(text("DELETE FROM courses"))
            await session.execute(text("DELETE FROM event_outbox"))
            await session.commit()

    @pytest.fixture
    async def timeout_monitor(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        mock_event_publisher: MockEventPublisher,
    ) -> AssociationTimeoutMonitor:
        """Create timeout monitor with real database session factory."""
        return AssociationTimeoutMonitor(
            session_factory=session_factory,
            event_publisher=mock_event_publisher,
        )

    async def create_test_course_and_class(
        self,
        session: AsyncSession,
        course_code: CourseCode = CourseCode.ENG5,
        class_name: str = "Test Class",
    ) -> tuple[Course, UserClass]:
        """Create test course and class in database."""
        # Create course
        course = Course(
            course_code=course_code,
            name=f"Test Course {course_code.value}",
            language=Language.ENGLISH,
        )
        session.add(course)
        await session.flush()

        # Create class
        user_class = UserClass(
            name=class_name,
            created_by_user_id="test_teacher_123",
            course_id=course.id,
        )
        session.add(user_class)
        await session.flush()

        return course, user_class

    async def create_test_students(
        self,
        session: AsyncSession,
        user_class: UserClass,
        count: int = 3,
    ) -> list[Student]:
        """Create test students and associate with class."""
        students = []
        # Use UUID to ensure unique emails across all tests
        unique_suffix = str(uuid4())[:8]
        for i in range(count):
            student = Student(
                first_name=f"Student{i}",
                last_name=f"Last{i}",
                email=f"student{i}.{unique_suffix}@test.com",
                created_by_user_id="test_teacher_123",
            )
            student.classes.append(user_class)
            session.add(student)
            students.append(student)

        await session.flush()
        return students

    async def create_association_with_old_timestamp(
        self,
        session: AsyncSession,
        batch_id: UUID,
        user_class: UserClass,
        student: Student,
        confidence_score: float,
        hours_old: int,
    ) -> EssayStudentAssociation:
        """Create association with manipulated created_at timestamp for timeout testing."""
        association = EssayStudentAssociation(
            essay_id=uuid4(),
            student_id=student.id,
            batch_id=batch_id,
            class_id=user_class.id,
            created_by_user_id="test_teacher_123",
            confidence_score=confidence_score,
            match_reasons={"similarity": confidence_score, "name_match": True},
            validation_status="pending_validation",
        )
        session.add(association)
        await session.flush()

        # Update timestamp directly in database to simulate old association
        # Use timezone-naive datetime to match database schema (TIMESTAMP WITHOUT TIME ZONE)
        old_timestamp = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours_old)
        await session.execute(
            update(EssayStudentAssociation)
            .where(EssayStudentAssociation.id == association.id)
            .values(created_at=old_timestamp)
        )
        await session.commit()

        # Refresh the object to get updated timestamp
        await session.refresh(association)
        return association

    async def setup_batch_with_mixed_confidence_associations(
        self,
        session: AsyncSession,
        course_code: CourseCode = CourseCode.ENG5,
        hours_old: int = 25,
    ) -> BatchTestData:
        """Set up a complete batch with high and low confidence associations."""
        # Create course and class
        course, user_class = await self.create_test_course_and_class(
            session, course_code=course_code
        )

        # Create students
        students = await self.create_test_students(session, user_class, count=4)

        # Create batch
        batch_id = uuid4()

        # Create associations with different confidence scores
        associations = []
        confidence_scores = [0.9, 0.8, 0.5, 0.3]  # 2 high, 2 low

        for i, confidence in enumerate(confidence_scores):
            association = await self.create_association_with_old_timestamp(
                session=session,
                batch_id=batch_id,
                user_class=user_class,
                student=students[i],
                confidence_score=confidence,
                hours_old=hours_old,
            )
            associations.append(association)

        return BatchTestData(
            batch_id=batch_id,
            course=course,
            user_class=user_class,
            students=students,
            associations=associations,
        )

    @pytest.mark.asyncio
    async def test_timeout_monitor_24_hour_trigger(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        session_factory: async_sessionmaker[AsyncSession],
        mock_event_publisher: MockEventPublisher,
    ):
        """
        Test that associations older than 24 hours are found and processed.

        Creates associations at various ages and verifies only those ≥24 hours
        are processed by the timeout monitor.
        """
        async with session_factory() as session:
            # Create test data with associations of different ages
            _, user_class = await self.create_test_course_and_class(session)
            students = await self.create_test_students(session, user_class, count=4)
            batch_id = uuid4()

            # Create associations with different ages
            ages_and_expectations = [
                (23, False),  # 23 hours - should NOT be processed
                (24, True),  # 24 hours exactly - should be processed
                (25, True),  # 25 hours - should be processed
                (48, True),  # 48 hours - should be processed
            ]

            associations = []
            for i, (hours_old, should_process) in enumerate(ages_and_expectations):
                association = await self.create_association_with_old_timestamp(
                    session=session,
                    batch_id=batch_id,
                    user_class=user_class,
                    student=students[i],
                    confidence_score=0.8,  # High confidence for all
                    hours_old=hours_old,
                )
                associations.append((association, should_process))

        # Run timeout processing
        await timeout_monitor._check_and_process_timeouts()

        # Verify results
        async with session_factory() as session:
            for association, should_process in associations:
                # Refresh association from database
                result = await session.execute(
                    select(EssayStudentAssociation).where(
                        EssayStudentAssociation.id == association.id
                    )
                )
                updated_association = result.scalar_one()

                if should_process:
                    # Should be confirmed
                    assert updated_association.validation_status == "confirmed"
                    assert (
                        updated_association.validation_method
                        == AssociationValidationMethod.TIMEOUT.value
                    )
                    assert updated_association.validated_by == "SYSTEM_TIMEOUT"
                    assert updated_association.validated_at is not None
                else:
                    # Should still be pending
                    assert updated_association.validation_status == "pending_validation"
                    assert updated_association.validated_at is None

        # Verify event was published for processed associations (3 out of 4)
        assert len(mock_event_publisher.published_events) == 1
        event = mock_event_publisher.published_events[0]
        assert event.batch_id == str(batch_id)
        assert len(event.associations) == 3  # Only the 3 old enough associations
        assert event.timeout_triggered is True

    @pytest.mark.asyncio
    async def test_high_confidence_auto_confirmation(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        session_factory: async_sessionmaker[AsyncSession],
        mock_event_publisher: MockEventPublisher,
    ):
        """
        Test that associations with ≥0.7 confidence are confirmed with original student.

        Creates associations with various high confidence scores and verifies
        they are all confirmed with their original student IDs.
        """
        async with session_factory() as session:
            # Create test data with high confidence associations
            batch_data = await self.setup_batch_with_mixed_confidence_associations(
                session, course_code=CourseCode.ENG7
            )

            # Filter to only high confidence associations for this test
            high_confidence_associations = [
                assoc
                for assoc in batch_data.associations
                if assoc.confidence_score is not None
                and assoc.confidence_score >= HIGH_CONFIDENCE_THRESHOLD
            ]
            original_student_ids = [assoc.student_id for assoc in high_confidence_associations]

        # Run timeout processing
        await timeout_monitor._check_and_process_timeouts()

        # Verify high confidence associations were confirmed with original students
        async with session_factory() as session:
            for i, association in enumerate(high_confidence_associations):
                result = await session.execute(
                    select(EssayStudentAssociation).where(
                        EssayStudentAssociation.id == association.id
                    )
                )
                updated_association = result.scalar_one()

                # Should be confirmed with original student
                assert updated_association.validation_status == "confirmed"
                assert updated_association.student_id == original_student_ids[i]
                assert (
                    updated_association.confidence_score is not None
                    and updated_association.confidence_score >= HIGH_CONFIDENCE_THRESHOLD
                )
                assert (
                    updated_association.validation_method
                    == AssociationValidationMethod.TIMEOUT.value
                )
                assert updated_association.validated_by == "SYSTEM_TIMEOUT"
                assert updated_association.validated_at is not None

        # Verify published event contains high confidence associations with original data
        assert len(mock_event_publisher.published_events) == 1
        event = mock_event_publisher.published_events[0]

        # Find high confidence associations in published event
        high_conf_event_assocs = [
            assoc
            for assoc in event.associations
            if assoc.confidence_score >= HIGH_CONFIDENCE_THRESHOLD
        ]

        assert len(high_conf_event_assocs) == len(high_confidence_associations)
        for assoc_data in high_conf_event_assocs:
            assert assoc_data.validation_method == AssociationValidationMethod.TIMEOUT
            assert assoc_data.validated_by == "SYSTEM_TIMEOUT"
            assert assoc_data.confidence_score >= HIGH_CONFIDENCE_THRESHOLD

    @pytest.mark.asyncio
    async def test_low_confidence_unknown_student_creation(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        session_factory: async_sessionmaker[AsyncSession],
        mock_event_publisher: MockEventPublisher,
    ):
        """
        Test that associations with <0.7 confidence create UNKNOWN student per class.

        Creates low confidence associations and verifies UNKNOWN students are
        created with proper attributes and class associations.
        """
        async with session_factory() as session:
            # Create test data with mixed confidence (focus on low confidence)
            batch_data = await self.setup_batch_with_mixed_confidence_associations(
                session, course_code=CourseCode.ENG5
            )

            # Filter to only low confidence associations for verification
            low_confidence_associations = [
                assoc
                for assoc in batch_data.associations
                if assoc.confidence_score is not None
                and assoc.confidence_score < HIGH_CONFIDENCE_THRESHOLD
            ]
            class_id = batch_data.user_class.id

        # Run timeout processing
        await timeout_monitor._check_and_process_timeouts()

        # Verify UNKNOWN student was created
        async with session_factory() as session:
            # Find UNKNOWN student for this class
            result = await session.execute(
                select(Student).where(
                    (Student.first_name == "UNKNOWN")
                    & (Student.last_name == "STUDENT")
                    & (Student.email == f"unknown.{class_id}@huleedu.system")
                    & (Student.classes.any(UserClass.id == class_id))
                )
            )
            unknown_student = result.scalar_one()

            # Verify UNKNOWN student properties
            assert unknown_student.first_name == "UNKNOWN"
            assert unknown_student.last_name == "STUDENT"
            assert unknown_student.email == f"unknown.{class_id}@huleedu.system"
            assert unknown_student.created_by_user_id == "SYSTEM_TIMEOUT"

            # Verify low confidence associations were updated to UNKNOWN student
            for association in low_confidence_associations:
                assoc_result = await session.execute(
                    select(EssayStudentAssociation).where(
                        EssayStudentAssociation.id == association.id
                    )
                )
                updated_association = assoc_result.scalar_one()

                assert updated_association.validation_status == "confirmed"
                assert updated_association.student_id == unknown_student.id
                assert (
                    updated_association.validation_method
                    == AssociationValidationMethod.TIMEOUT.value
                )
                assert updated_association.validated_by == "SYSTEM_TIMEOUT"

        # Verify published event contains UNKNOWN student associations
        assert len(mock_event_publisher.published_events) == 1
        event = mock_event_publisher.published_events[0]

        # Find low confidence associations in published event (now with confidence_score=0.0)
        unknown_assocs = [assoc for assoc in event.associations if assoc.confidence_score == 0.0]

        assert len(unknown_assocs) == len(low_confidence_associations)
        for assoc_data in unknown_assocs:
            assert assoc_data.validation_method == AssociationValidationMethod.TIMEOUT
            assert assoc_data.validated_by == "SYSTEM_TIMEOUT"
            assert assoc_data.confidence_score == 0.0  # Reset for UNKNOWN

    @pytest.mark.asyncio
    async def test_multiple_batches_timeout_together(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        session_factory: async_sessionmaker[AsyncSession],
        mock_event_publisher: MockEventPublisher,
    ):
        """
        Test that multiple batches with different classes timeout independently.

        Creates multiple batches with different course codes and verifies each
        batch is processed independently with proper isolation.
        """
        async with session_factory() as session:
            # Create 3 different batches with different courses
            batch_configs = [
                CourseCode.ENG5,
                CourseCode.ENG7,
                CourseCode.SV3,
            ]

            batch_data_list = []
            for course_code in batch_configs:
                batch_data = await self.setup_batch_with_mixed_confidence_associations(
                    session, course_code=course_code, hours_old=30
                )
                batch_data_list.append(batch_data)

            # Commit all test data to ensure it's visible to timeout monitor
            await session.commit()

        # Run timeout processing (should process all batches)
        await timeout_monitor._check_and_process_timeouts()

        # Verify each batch was processed independently
        assert len(mock_event_publisher.published_events) == 3

        # Verify each event corresponds to correct batch and course
        published_batch_ids = {event.batch_id for event in mock_event_publisher.published_events}
        expected_batch_ids = {str(batch_data.batch_id) for batch_data in batch_data_list}
        assert published_batch_ids == expected_batch_ids

        for event in mock_event_publisher.published_events:
            # Find corresponding batch data
            batch_data = next(bd for bd in batch_data_list if str(bd.batch_id) == event.batch_id)

            # Verify event data matches batch
            assert event.course_code == batch_data.course.course_code
            assert event.class_id == str(batch_data.user_class.id)
            assert event.timeout_triggered is True
            assert len(event.associations) == 4  # All 4 associations per batch

        # Verify UNKNOWN students created per class (not shared across batches)
        async with session_factory() as session:
            for batch_data in batch_data_list:
                # Count UNKNOWN students for this class
                result = await session.execute(
                    select(Student).where(
                        (Student.first_name == "UNKNOWN")
                        & (Student.last_name == "STUDENT")
                        & (Student.classes.any(UserClass.id == batch_data.user_class.id))
                    )
                )
                unknown_students = result.scalars().all()

                # Should be exactly 1 UNKNOWN student per class
                assert len(unknown_students) == 1
                assert (
                    unknown_students[0].email
                    == f"unknown.{batch_data.user_class.id}@huleedu.system"
                )

    @pytest.mark.asyncio
    async def test_timeout_event_propagation(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        session_factory: async_sessionmaker[AsyncSession],
        mock_event_publisher: MockEventPublisher,
    ):
        """
        Test that StudentAssociationsConfirmedV1 events contain proper cross-service data.

        Verifies published events have all required fields for downstream
        services including proper course_code propagation and correlation IDs.
        """
        async with session_factory() as session:
            # Create batch with known course code for verification
            batch_data = await self.setup_batch_with_mixed_confidence_associations(
                session, course_code=CourseCode.ENG7, hours_old=30
            )

        # Run timeout processing
        await timeout_monitor._check_and_process_timeouts()

        # Verify event structure and data
        assert len(mock_event_publisher.published_events) == 1
        event = mock_event_publisher.published_events[0]

        # Verify core event fields
        assert event.batch_id == str(batch_data.batch_id)
        assert event.class_id == str(batch_data.user_class.id)
        assert event.course_code == CourseCode.ENG7
        assert event.timeout_triggered is True

        # Verify validation summary
        assert "confirmed" in event.validation_summary
        assert event.validation_summary["confirmed"] == 4  # All 4 associations
        assert event.validation_summary["rejected"] == 0

        # Verify association data completeness
        assert len(event.associations) == 4
        for assoc_data in event.associations:
            # Required fields for downstream services
            assert assoc_data.essay_id is not None
            assert assoc_data.student_id is not None
            assert assoc_data.confidence_score is not None
            assert assoc_data.validation_method is not None
            assert assoc_data.validated_by is not None
            assert assoc_data.validated_at is not None

            # Timeout-specific values
            assert assoc_data.validation_method == AssociationValidationMethod.TIMEOUT
            assert assoc_data.validated_by == "SYSTEM_TIMEOUT"
            assert assoc_data.validated_at is not None

        # Verify publish call included correlation_id
        assert len(mock_event_publisher.publish_calls) == 1
        publish_call = mock_event_publisher.publish_calls[0]
        assert "correlation_id" in publish_call
        assert isinstance(publish_call["correlation_id"], UUID)
        assert publish_call["timeout_triggered"] is True
        assert publish_call["course_code"] == CourseCode.ENG7
