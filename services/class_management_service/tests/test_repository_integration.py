"""
Integration tests for repository async session management with real PostgreSQL.

Tests the actual async session patterns that prevent DetachedInstanceError
and MissingGreenlet issues using testcontainers for real database operations.

Following HuleEdu testing patterns from research analysis.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator

import pytest
from common_core.domain_enums import CourseCode
from common_core.metadata_models import PersonNameV1
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.class_management_service.api_models import (
    CreateClassRequest,
    CreateStudentRequest,
    UpdateStudentRequest,
)
from services.class_management_service.implementations.class_repository_postgres_impl import (
    PostgreSQLClassRepositoryImpl,
)
from services.class_management_service.models_db import Base, Student, UserClass


class TestRepositoryIntegration:
    """Integration tests for repository with real PostgreSQL database."""

    @pytest.fixture(scope="function")
    def postgres_container(self) -> PostgresContainer:
        """Provide PostgreSQL testcontainer for testing."""
        with PostgresContainer("postgres:15") as container:
            yield container

    @pytest.fixture(scope="function")
    async def async_engine(
        self, postgres_container: PostgresContainer
    ) -> AsyncGenerator[AsyncEngine, None]:
        """Create async engine with testcontainer database."""
        # Get connection URL and convert to asyncpg
        conn_url = postgres_container.get_connection_url()
        if "+psycopg2://" in conn_url:
            conn_url = conn_url.replace("+psycopg2://", "+asyncpg://")

        engine = create_async_engine(conn_url, echo=False, pool_size=5, max_overflow=0)

        # Create database schema
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            # Seed courses (essential for class creation)
            await conn.execute(
                text("""
                INSERT INTO courses (id, course_code, name, language) VALUES
                (gen_random_uuid(), 'ENG5', 'English 5', 'en'),
                (gen_random_uuid(), 'ENG6', 'English 6', 'en'),
                (gen_random_uuid(), 'ENG7', 'English 7', 'en'),
                (gen_random_uuid(), 'SV1', 'Svenska 1', 'sv'),
                (gen_random_uuid(), 'SV2', 'Svenska 2', 'sv'),
                (gen_random_uuid(), 'SV3', 'Svenska 3', 'sv')
                ON CONFLICT (course_code) DO NOTHING
            """)
            )

        try:
            yield engine
        finally:
            await engine.dispose()

    @pytest.fixture
    def repository(self, async_engine: AsyncEngine) -> PostgreSQLClassRepositoryImpl:
        """Create repository with real database engine."""
        return PostgreSQLClassRepositoryImpl[UserClass, Student](async_engine, None)

    @pytest.mark.asyncio
    async def test_create_class_with_real_database(
        self, repository: PostgreSQLClassRepositoryImpl
    ) -> None:
        """Test class creation with real database and async session management."""
        # Arrange
        class_data = CreateClassRequest(
            name="Integration Test Class", course_codes=[CourseCode.ENG5]
        )
        user_id = "integration-test-user"

        # Act
        correlation_id = uuid.uuid4()
        created_class = await repository.create_class(user_id, class_data, correlation_id)

        # Assert
        assert created_class.id is not None
        assert created_class.name == "Integration Test Class"
        assert created_class.course.course_code == CourseCode.ENG5

        # Verify we can retrieve the class (tests eager loading)
        retrieved_class = await repository.get_class_by_id(created_class.id)
        assert retrieved_class is not None
        assert retrieved_class.id == created_class.id
        assert retrieved_class.name == "Integration Test Class"

        # Verify no DetachedInstanceError when accessing relationships
        assert retrieved_class.course.course_code == CourseCode.ENG5

    @pytest.mark.asyncio
    async def test_create_student_eager_loading_prevention(
        self, repository: PostgreSQLClassRepositoryImpl
    ) -> None:
        """Test student creation with eager loading to prevent DetachedInstanceError."""
        # Arrange
        student_data = CreateStudentRequest(
            person_name=PersonNameV1(first_name="Integration", last_name="Student"),
            email="integration.student@example.com",
        )
        user_id = "integration-test-user"

        # Act
        correlation_id = uuid.uuid4()
        created_student = await repository.create_student(user_id, student_data, correlation_id)

        # Assert - test the critical DetachedInstanceError prevention
        assert created_student.id is not None
        assert created_student.first_name == "Integration"
        assert created_student.last_name == "Student"
        assert created_student.email == "integration.student@example.com"

        # CRITICAL: Access classes relationship
        # (this would cause DetachedInstanceError if not properly eager loaded)
        assert created_student.classes is not None
        assert len(created_student.classes) == 0  # New student, no classes yet

        # Verify we can retrieve the student and access relationships
        retrieved_student = await repository.get_student_by_id(created_student.id)
        assert retrieved_student is not None
        assert retrieved_student.classes is not None  # Should not raise DetachedInstanceError

    @pytest.mark.asyncio
    async def test_concurrent_session_isolation(self, async_engine: AsyncEngine) -> None:
        """Test that concurrent repository operations use isolated sessions."""
        # Arrange - create multiple repository instances
        repo1 = PostgreSQLClassRepositoryImpl[UserClass, Student](async_engine, None)
        repo2 = PostgreSQLClassRepositoryImpl[UserClass, Student](async_engine, None)

        class_data1 = CreateClassRequest(name="Concurrent Class 1", course_codes=[CourseCode.ENG5])
        class_data2 = CreateClassRequest(name="Concurrent Class 2", course_codes=[CourseCode.SV1])

        # Act - run concurrent operations
        correlation_id1 = uuid.uuid4()
        correlation_id2 = uuid.uuid4()
        results = await asyncio.gather(
            repo1.create_class("user1", class_data1, correlation_id1),
            repo2.create_class("user2", class_data2, correlation_id2),
            return_exceptions=True,
        )

        # Assert - both operations should succeed with different IDs
        class1, class2 = results
        assert not isinstance(class1, Exception), f"Repo1 failed: {class1}"
        assert not isinstance(class2, Exception), f"Repo2 failed: {class2}"

        # Type narrowing for mypy
        assert isinstance(class1, UserClass)
        assert isinstance(class2, UserClass)

        assert class1.id != class2.id
        assert class1.name == "Concurrent Class 1"
        assert class2.name == "Concurrent Class 2"
        assert class1.course.course_code == CourseCode.ENG5
        assert class2.course.course_code == CourseCode.SV1

    @pytest.mark.asyncio
    async def test_session_error_handling_and_rollback(
        self, repository: PostgreSQLClassRepositoryImpl
    ) -> None:
        """Test session error handling and rollback behavior."""
        # Arrange - invalid course code that should cause error
        invalid_class_data = CreateClassRequest(
            name="Error Test Class",
            course_codes=[CourseCode.ENG5, CourseCode.SV1],  # Multiple courses should fail
        )
        user_id = "error-test-user"

        # Act & Assert - should raise HuleEduError
        from common_core.error_enums import ClassManagementErrorCode
        from huleedu_service_libs.error_handling import HuleEduError

        correlation_id = uuid.uuid4()
        with pytest.raises(HuleEduError) as exc_info:
            await repository.create_class(user_id, invalid_class_data, correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == ClassManagementErrorCode.MULTIPLE_COURSE_ERROR

        # Verify database is in clean state (transaction was rolled back)
        # Create a valid class to ensure database is still functional
        valid_class_data = CreateClassRequest(
            name="Recovery Test Class", course_codes=[CourseCode.ENG5]
        )
        new_correlation_id = uuid.uuid4()
        recovered_class = await repository.create_class(
            user_id, valid_class_data, new_correlation_id
        )
        assert recovered_class.name == "Recovery Test Class"

    @pytest.mark.asyncio
    async def test_update_operations_with_real_database(
        self, repository: PostgreSQLClassRepositoryImpl
    ) -> None:
        """Test update operations maintain async session patterns."""
        # Arrange - create a student first
        student_data = CreateStudentRequest(
            person_name=PersonNameV1(first_name="Original", last_name="Name"),
            email="original@example.com",
        )
        correlation_id = uuid.uuid4()
        created_student = await repository.create_student("test-user", student_data, correlation_id)

        # Act - update the student
        update_data = UpdateStudentRequest(
            person_name=PersonNameV1(first_name="Updated", last_name="Name"),
            email="updated@example.com",
        )
        updated_student = await repository.update_student(
            created_student.id, update_data, correlation_id
        )

        # Assert
        assert updated_student is not None
        assert updated_student.id == created_student.id
        assert updated_student.first_name == "Updated"
        assert updated_student.email == "updated@example.com"

        # Verify relationships are still accessible (no DetachedInstanceError)
        assert updated_student.classes is not None

    @pytest.mark.asyncio
    async def test_delete_operations_with_real_database(
        self, repository: PostgreSQLClassRepositoryImpl
    ) -> None:
        """Test delete operations follow proper async session patterns."""
        # Arrange - create a class to delete
        class_data = CreateClassRequest(name="Delete Test Class", course_codes=[CourseCode.ENG5])
        correlation_id = uuid.uuid4()
        created_class = await repository.create_class("test-user", class_data, correlation_id)

        # Act - delete the class
        delete_result = await repository.delete_class(created_class.id)

        # Assert
        assert delete_result is True

        # Verify class is deleted
        retrieved_class = await repository.get_class_by_id(created_class.id)
        assert retrieved_class is None

    @pytest.mark.asyncio
    async def test_multiple_course_validation_with_database(
        self, repository: PostgreSQLClassRepositoryImpl
    ) -> None:
        """Test course validation logic with real database."""
        # Test that multiple courses raise appropriate error
        from common_core.error_enums import ClassManagementErrorCode
        from huleedu_service_libs.error_handling import HuleEduError

        multiple_course_data = CreateClassRequest(
            name="Multiple Course Class",
            course_codes=[CourseCode.ENG5, CourseCode.SV1, CourseCode.ENG6],
        )

        correlation_id = uuid.uuid4()
        with pytest.raises(HuleEduError) as exc_info:
            await repository.create_class("test-user", multiple_course_data, correlation_id)

        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == ClassManagementErrorCode.MULTIPLE_COURSE_ERROR
        assert len(error_detail.details["provided_course_codes"]) == 3
        assert "ENG5" in error_detail.details["provided_course_codes"]
        assert "SV1" in error_detail.details["provided_course_codes"]
        assert "ENG6" in error_detail.details["provided_course_codes"]

    @pytest.mark.asyncio
    async def test_database_schema_initialization(self, async_engine: AsyncEngine) -> None:
        """Test that database schema is properly initialized."""
        # Verify tables exist
        async with async_engine.begin() as conn:
            # Check that courses table has expected data
            result = await conn.execute(
                text("SELECT course_code FROM courses ORDER BY course_code")
            )
            course_codes = [row[0] for row in result.fetchall()]

            # Should have seeded courses
            assert "ENG5" in course_codes
            assert "SV1" in course_codes
            assert len(course_codes) == 6
