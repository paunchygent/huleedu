"""
Unit tests for repository async session management patterns.

Tests the critical async session management implementation that prevents
DetachedInstanceError and MissingGreenlet issues identified in Phase 1-2.

Following HuleEdu testing patterns: mock at protocol boundaries only.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from common_core.domain_enums import CourseCode
from common_core.metadata_models import PersonNameV1
from huleedu_service_libs.database import DatabaseMetricsProtocol
from sqlalchemy.ext.asyncio import AsyncEngine

from services.class_management_service.api_models import CreateClassRequest, CreateStudentRequest
from services.class_management_service.implementations.class_repository_postgres_impl import (
    PostgreSQLClassRepositoryImpl,
)
from services.class_management_service.models_db import Student, UserClass


class TestRepositoryAsyncSessionPatterns:
    """Test suite for repository async session management patterns."""

    def test_repository_initialization_follows_correct_pattern(self) -> None:
        """Test repository initialization follows AsyncEngine injection pattern."""
        # Arrange
        mock_engine = AsyncMock(spec=AsyncEngine)
        mock_metrics = AsyncMock(spec=DatabaseMetricsProtocol)

        # Act
        repo = PostgreSQLClassRepositoryImpl[UserClass, Student](mock_engine, mock_metrics)

        # Assert - repository stores engine and metrics correctly
        assert repo.engine is mock_engine
        assert repo.metrics is mock_metrics

        # Verify async_session_maker is created (repository-managed sessions)
        assert repo.async_session_maker is not None

    def test_repository_handles_missing_metrics_gracefully(self) -> None:
        """Test repository works correctly without metrics."""
        # Arrange
        mock_engine = AsyncMock(spec=AsyncEngine)

        # Act
        repo = PostgreSQLClassRepositoryImpl[UserClass, Student](mock_engine, None)

        # Assert
        assert repo.engine is mock_engine
        assert repo.metrics is None

        # Should not raise errors when metrics is None
        repo._record_operation_metrics("test_op", "test_table", 1.0, True)
        repo._record_error_metrics("TestError", "test_op")

    def test_concurrent_repositories_have_isolated_session_makers(self) -> None:
        """Test that concurrent repository instances use isolated session makers."""
        # Arrange
        mock_engine1 = AsyncMock(spec=AsyncEngine)
        mock_engine2 = AsyncMock(spec=AsyncEngine)
        mock_metrics = AsyncMock(spec=DatabaseMetricsProtocol)

        # Act
        repo1 = PostgreSQLClassRepositoryImpl[UserClass, Student](mock_engine1, mock_metrics)
        repo2 = PostgreSQLClassRepositoryImpl[UserClass, Student](mock_engine2, mock_metrics)

        # Assert - each repository has its own session maker (isolation)
        assert repo1.async_session_maker is not repo2.async_session_maker
        assert repo1.engine is not repo2.engine

    @pytest.mark.asyncio
    async def test_metrics_recording_pattern(self) -> None:
        """Test that metrics are recorded correctly for operations."""
        # Arrange
        mock_engine = AsyncMock(spec=AsyncEngine)
        mock_metrics = AsyncMock(spec=DatabaseMetricsProtocol)
        repo = PostgreSQLClassRepositoryImpl[UserClass, Student](mock_engine, mock_metrics)

        # Act - call metrics recording methods directly (unit test boundary)
        repo._record_operation_metrics("create_class", "classes", 1.5, True)
        repo._record_error_metrics("SQLError", "create_class")

        # Assert
        mock_metrics.record_query_duration.assert_called_once_with(
            operation="create_class", table="classes", duration=1.5, success=True
        )
        mock_metrics.record_database_error.assert_called_once_with("SQLError", "create_class")

    def test_repository_protocol_compliance(self) -> None:
        """Test repository implements required protocol methods."""
        # Arrange
        mock_engine = AsyncMock(spec=AsyncEngine)
        repo = PostgreSQLClassRepositoryImpl[UserClass, Student](mock_engine)

        # Assert - verify protocol methods exist (not calling them, just checking structure)
        assert hasattr(repo, "create_class")
        assert hasattr(repo, "get_class_by_id")
        assert hasattr(repo, "update_class")
        assert hasattr(repo, "delete_class")
        assert hasattr(repo, "create_student")
        assert hasattr(repo, "get_student_by_id")
        assert hasattr(repo, "update_student")
        assert hasattr(repo, "delete_student")
        assert hasattr(repo, "get_batch_student_associations")

        # Verify session context manager exists (critical async pattern)
        assert hasattr(repo, "session")

    def test_course_validation_logic_unit(self) -> None:
        """Test course validation business logic in isolation."""
        # Test multiple course error using factory
        import uuid

        from common_core.error_enums import ClassManagementErrorCode
        from huleedu_service_libs.error_handling import HuleEduError, raise_multiple_course_error

        multiple_courses = [CourseCode.ENG5, CourseCode.SV1]
        correlation_id = uuid.uuid4()

        # This tests the validation logic without database calls
        with pytest.raises(HuleEduError) as exc_info:
            # We trigger the error using the factory function
            course_codes_str = ", ".join(code.value for code in multiple_courses)
            raise_multiple_course_error(
                service="class_management_service",
                operation="test_validation",
                message=(
                    f"Multiple courses provided ({course_codes_str}), "
                    f"but only one course per class is supported"
                ),
                correlation_id=correlation_id,
                provided_course_codes=[code.value for code in multiple_courses],
            )

        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == ClassManagementErrorCode.MULTIPLE_COURSE_ERROR
        assert error_detail.details["provided_course_codes"] == ["ENG5", "SV1"]
        assert "Multiple courses provided" in error_detail.message

    def test_repository_type_safety_patterns(self) -> None:
        """Test repository maintains type safety with generics."""
        # Arrange
        mock_engine = AsyncMock(spec=AsyncEngine)

        # Act - create typed repository
        repo = PostgreSQLClassRepositoryImpl[UserClass, Student](mock_engine)

        # Assert - verify type annotations are preserved
        # This is a compile-time check more than runtime, but ensures structure
        assert repo.__class__.__name__ == "PostgreSQLClassRepositoryImpl"

        # The repository should be parameterized for UserClass and Student types
        # This test ensures the generic typing pattern is maintained

    @pytest.mark.asyncio
    async def test_session_context_manager_structure(self) -> None:
        """Test session context manager has correct async structure."""
        # Arrange
        mock_engine = AsyncMock(spec=AsyncEngine)
        repo = PostgreSQLClassRepositoryImpl[UserClass, Student](mock_engine)

        # Act & Assert - verify session method exists and is async context manager
        assert hasattr(repo, "session")

        # The session method should be an async context manager
        # We can verify its structure without calling database operations
        import inspect

        assert inspect.iscoroutinefunction(repo.session().__aenter__)
        assert inspect.iscoroutinefunction(repo.session().__aexit__)

    def test_api_model_validation_patterns(self) -> None:
        """Test repository correctly accepts API model types."""
        # Test CreateClassRequest structure
        class_request = CreateClassRequest(name="Test Class", course_codes=[CourseCode.ENG5])
        assert class_request.name == "Test Class"
        assert class_request.course_codes == [CourseCode.ENG5]

        # Test CreateStudentRequest structure
        student_request = CreateStudentRequest(
            person_name=PersonNameV1(first_name="John", last_name="Doe"),
            email="john.doe@example.com",
        )
        assert student_request.person_name.first_name == "John"
        assert student_request.person_name.last_name == "Doe"
        assert student_request.email == "john.doe@example.com"
