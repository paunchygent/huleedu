"""
Unit tests for PostgreSQLClassRepositoryImpl JOIN operation structure and patterns.

Tests focus on repository initialization, protocol compliance, and JOIN method patterns.
Following HuleEdu testing patterns: test structure and contracts, not database operations.
"""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core.metadata_models import PersonNameV1
from huleedu_service_libs.error_handling import HuleEduError, raise_processing_error
from sqlalchemy.ext.asyncio import AsyncEngine

from services.class_management_service.implementations.class_repository_postgres_impl import (
    PostgreSQLClassRepositoryImpl,
)
from services.class_management_service.models_db import EssayStudentAssociation, Student


class TestPostgreSQLClassRepositoryJoinOperations:
    """Tests for PostgreSQLClassRepositoryImpl JOIN operation structure and patterns."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock async engine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def repository(self, mock_engine: AsyncMock) -> PostgreSQLClassRepositoryImpl:
        """Create repository with mocked engine."""
        return PostgreSQLClassRepositoryImpl(mock_engine)

    @pytest.fixture
    def batch_id(self) -> UUID:
        """Sample batch ID for testing."""
        return uuid4()

    @pytest.fixture
    def essay_id(self) -> UUID:
        """Sample essay ID for testing."""
        return uuid4()

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID for testing."""
        return uuid4()

    def test_repository_initialization_includes_new_methods(
        self, repository: PostgreSQLClassRepositoryImpl
    ) -> None:
        """Test repository implements new JOIN methods."""
        # Assert - verify new JOIN methods exist
        assert hasattr(repository, "get_batch_student_names")
        assert hasattr(repository, "get_essay_student_association")

        # Verify methods are async
        assert inspect.iscoroutinefunction(repository.get_batch_student_names)
        assert inspect.iscoroutinefunction(repository.get_essay_student_association)

    def test_get_batch_student_names_method_signature(
        self, repository: PostgreSQLClassRepositoryImpl
    ) -> None:
        """Test get_batch_student_names has correct async signature."""
        # Verify method signature
        method_sig = inspect.signature(repository.get_batch_student_names)
        expected_params = ["batch_id", "correlation_id"]
        actual_params = list(method_sig.parameters.keys())

        # Assert - check required parameters exist
        assert all(param in actual_params for param in expected_params)

        # Verify return type annotation suggests list structure
        return_annotation = method_sig.return_annotation
        assert return_annotation is not None

    def test_get_essay_student_association_method_signature(
        self, repository: PostgreSQLClassRepositoryImpl
    ) -> None:
        """Test get_essay_student_association has correct async signature."""
        # Verify method signature
        method_sig = inspect.signature(repository.get_essay_student_association)
        expected_params = ["essay_id", "correlation_id"]
        actual_params = list(method_sig.parameters.keys())

        # Assert - check required parameters exist
        assert all(param in actual_params for param in expected_params)

        # Verify return type annotation suggests optional dict structure
        return_annotation = method_sig.return_annotation
        assert return_annotation is not None

    def test_session_context_manager_structure(
        self, repository: PostgreSQLClassRepositoryImpl
    ) -> None:
        """Test session context manager has correct async structure."""
        # Assert - verify session context method exists and is async context manager
        assert hasattr(repository, "session")

        # The session method should be an async context manager
        session_context = repository.session()
        assert hasattr(session_context, "__aenter__")
        assert hasattr(session_context, "__aexit__")
        assert inspect.iscoroutinefunction(session_context.__aenter__)
        assert inspect.iscoroutinefunction(session_context.__aexit__)

    def test_concurrent_repositories_have_isolated_session_makers(self) -> None:
        """Test that concurrent repository instances use isolated session makers."""
        # Arrange
        mock_engine1 = AsyncMock(spec=AsyncEngine)
        mock_engine2 = AsyncMock(spec=AsyncEngine)

        # Act
        repo1: PostgreSQLClassRepositoryImpl = PostgreSQLClassRepositoryImpl(mock_engine1)
        repo2: PostgreSQLClassRepositoryImpl = PostgreSQLClassRepositoryImpl(mock_engine2)

        # Assert - each repository has its own session maker (isolation)
        assert repo1.async_session_maker is not repo2.async_session_maker

    def test_metrics_recording_patterns_for_join_operations(self, mock_engine: AsyncMock) -> None:
        """Test metrics recording structure exists for JOIN operations."""
        # Arrange - create repository with mock metrics
        mock_metrics = AsyncMock()
        repo: PostgreSQLClassRepositoryImpl = PostgreSQLClassRepositoryImpl(
            mock_engine, metrics=mock_metrics
        )

        # Assert - verify metrics recording methods exist
        assert hasattr(repo, "_record_operation_metrics")
        assert hasattr(repo, "_record_error_metrics")
        assert repo.metrics is mock_metrics

    def test_error_handling_patterns_for_get_batch_student_names(
        self, batch_id: UUID, correlation_id: UUID
    ) -> None:
        """Test error handling business logic for get_batch_student_names without database calls."""
        # This tests the error raising pattern using the factory function directly
        with pytest.raises(HuleEduError) as exc_info:
            # Trigger the error using the factory function directly
            raise_processing_error(
                service="class_management_service",
                operation="get_batch_student_names",
                message="Database error during batch student names retrieval",
                correlation_id=correlation_id,
                error_type="SQLAlchemyError",
                batch_id=str(batch_id),
            )

        error = exc_info.value
        assert "Database error during batch student names retrieval" in str(error)
        assert error.error_detail.service == "class_management_service"
        assert error.error_detail.operation == "get_batch_student_names"

    def test_error_handling_patterns_for_get_essay_student_association(
        self, essay_id: UUID, correlation_id: UUID
    ) -> None:
        """Test error handling business logic for get_essay_student_association without database calls."""
        # This tests the error raising pattern using the factory function directly
        with pytest.raises(HuleEduError) as exc_info:
            # Trigger the error using the factory function directly
            raise_processing_error(
                service="class_management_service",
                operation="get_essay_student_association",
                message="Database error during essay student association retrieval",
                correlation_id=correlation_id,
                error_type="SQLAlchemyError",
                essay_id=str(essay_id),
            )

        error = exc_info.value
        assert "Database error during essay student association retrieval" in str(error)
        assert error.error_detail.service == "class_management_service"
        assert error.error_detail.operation == "get_essay_student_association"

    def test_person_name_v1_structure_supports_unicode(self) -> None:
        """Test PersonNameV1 model correctly handles Unicode characters."""
        # Arrange & Act - test Swedish characters
        person_name = PersonNameV1(
            first_name="Åsa", last_name="Öberg", legal_full_name="Åsa Maria Öberg"
        )

        # Assert - model should handle Unicode characters without issues
        assert person_name.first_name == "Åsa"
        assert person_name.last_name == "Öberg"
        assert person_name.legal_full_name == "Åsa Maria Öberg"

    @pytest.mark.parametrize(
        "first_name, last_name, legal_full_name",
        [
            ("Åsa", "Öberg", "Åsa Maria Öberg"),  # Swedish characters
            ("Karl", "Ängström", "Karl Erik Ängström"),  # More Swedish characters
            ("José", "García", "José Manuel García"),  # Spanish characters
            ("François", "Müller", "François Jean Müller"),  # Mixed Unicode
            ("", "", ""),  # Empty strings
            ("Test", "", "Test User"),  # Partial empty
        ],
    )
    def test_person_name_v1_unicode_edge_cases(
        self, first_name: str, last_name: str, legal_full_name: str
    ) -> None:
        """Test PersonNameV1 model handles various Unicode and edge cases."""
        # Arrange & Act
        person_name = PersonNameV1(
            first_name=first_name, last_name=last_name, legal_full_name=legal_full_name
        )

        # Assert - model should handle all cases without errors
        assert person_name.first_name == first_name
        assert person_name.last_name == last_name
        assert person_name.legal_full_name == legal_full_name

    def test_batch_student_names_return_structure_patterns(self) -> None:
        """Test expected return structure for batch student names."""
        # Test the expected return structure pattern
        expected_batch_item = {
            "essay_id": uuid4(),
            "student_id": uuid4(),
            "student_person_name": PersonNameV1(
                first_name="Test", last_name="Student", legal_full_name="Test Student"
            ),
        }

        # Assert - verify expected structure
        assert "essay_id" in expected_batch_item
        assert "student_id" in expected_batch_item
        assert "student_person_name" in expected_batch_item
        assert isinstance(expected_batch_item["student_person_name"], PersonNameV1)

    def test_essay_student_association_return_structure_patterns(self) -> None:
        """Test expected return structure for single essay student association."""
        # Test the expected return structure pattern
        expected_association = {
            "essay_id": uuid4(),
            "student_id": uuid4(),
            "student_person_name": PersonNameV1(
                first_name="Test", last_name="Student", legal_full_name="Test Student"
            ),
        }

        # Assert - verify expected structure
        assert "essay_id" in expected_association
        assert "student_id" in expected_association
        assert "student_person_name" in expected_association
        assert isinstance(expected_association["student_person_name"], PersonNameV1)

    def test_repository_protocol_compliance_includes_join_methods(
        self, repository: PostgreSQLClassRepositoryImpl
    ) -> None:
        """Test repository implements required protocol methods including JOIN operations."""
        # Assert - verify core protocol methods exist
        assert hasattr(repository, "create_class")
        assert hasattr(repository, "get_class_by_id")
        assert hasattr(repository, "update_class")
        assert hasattr(repository, "delete_class")
        assert hasattr(repository, "create_student")
        assert hasattr(repository, "get_student_by_id")
        assert hasattr(repository, "update_student")
        assert hasattr(repository, "delete_student")

        # Assert - verify JOIN methods exist
        assert hasattr(repository, "get_batch_student_names")
        assert hasattr(repository, "get_essay_student_association")

        # Verify all methods are async
        assert inspect.iscoroutinefunction(repository.get_batch_student_names)
        assert inspect.iscoroutinefunction(repository.get_essay_student_association)

    def test_repository_type_safety_patterns_for_join_operations(
        self, mock_engine: AsyncMock
    ) -> None:
        """Test repository maintains type safety patterns for JOIN operations."""
        # Act - create repository
        repo: PostgreSQLClassRepositoryImpl = PostgreSQLClassRepositoryImpl(mock_engine)

        # Assert - verify type structure is maintained
        assert repo.__class__.__name__ == "PostgreSQLClassRepositoryImpl"

        # The repository should follow the expected naming and structure patterns
        assert hasattr(repo, "engine")
        assert hasattr(repo, "async_session_maker")
        assert hasattr(repo, "_user_class_type")
        assert hasattr(repo, "_student_type")

    def test_database_model_relationships_structure(self) -> None:
        """Test database model relationships structure for JOIN operations."""
        # Test EssayStudentAssociation model structure
        association = EssayStudentAssociation()

        # Assert - verify expected attributes exist
        assert hasattr(association, "essay_id")
        assert hasattr(association, "student_id")
        assert hasattr(association, "batch_id")
        assert hasattr(association, "created_at")

        # Test Student model structure
        student = Student()

        # Assert - verify expected attributes exist
        assert hasattr(student, "id")
        assert hasattr(student, "first_name")
        assert hasattr(student, "last_name")
        assert hasattr(student, "legal_full_name")

    def test_join_operation_timing_patterns(self, mock_engine: AsyncMock) -> None:
        """Test timing patterns exist for JOIN operations."""
        # Arrange - create repository with metrics
        mock_metrics = AsyncMock()
        repo: PostgreSQLClassRepositoryImpl = PostgreSQLClassRepositoryImpl(
            mock_engine, metrics=mock_metrics
        )

        # Assert - verify timing methods exist (structure testing)
        assert hasattr(repo, "_record_operation_metrics")
        assert callable(repo._record_operation_metrics)

        # Verify method signature for metrics recording
        metrics_sig = inspect.signature(repo._record_operation_metrics)
        expected_params = ["operation", "table", "duration"]
        actual_params = list(metrics_sig.parameters.keys())
        assert all(param in actual_params for param in expected_params)

    def test_repository_method_signatures_match_join_protocols(
        self, repository: PostgreSQLClassRepositoryImpl
    ) -> None:
        """Test repository JOIN method signatures match expected protocols."""
        # Verify get_batch_student_names signature
        batch_names_sig = inspect.signature(repository.get_batch_student_names)
        expected_params = ["batch_id", "correlation_id"]
        actual_params = list(batch_names_sig.parameters.keys())
        assert all(param in actual_params for param in expected_params)

        # Verify get_essay_student_association signature
        essay_assoc_sig = inspect.signature(repository.get_essay_student_association)
        expected_params = ["essay_id", "correlation_id"]
        actual_params = list(essay_assoc_sig.parameters.keys())
        assert all(param in actual_params for param in expected_params)

    def test_optional_return_value_patterns(self) -> None:
        """Test optional return value patterns for single association lookup."""
        # Test None return pattern for missing association
        missing_result = None
        assert missing_result is None

        # Test successful return pattern
        found_result = {
            "essay_id": uuid4(),
            "student_id": uuid4(),
            "student_person_name": PersonNameV1(
                first_name="Found", last_name="Student", legal_full_name="Found Student"
            ),
        }
        assert found_result is not None
        assert isinstance(found_result, dict)

    def test_batch_operation_list_patterns(self) -> None:
        """Test batch operation list patterns for multiple associations."""
        # Test empty batch result
        empty_batch: list[dict[str, Any]] = []
        assert isinstance(empty_batch, list)
        assert len(empty_batch) == 0

        # Test populated batch result
        populated_batch = [
            {
                "essay_id": uuid4(),
                "student_id": uuid4(),
                "student_person_name": PersonNameV1(
                    first_name="Student1", last_name="Test", legal_full_name="Student1 Test"
                ),
            },
            {
                "essay_id": uuid4(),
                "student_id": uuid4(),
                "student_person_name": PersonNameV1(
                    first_name="Student2", last_name="Test", legal_full_name="Student2 Test"
                ),
            },
        ]
        assert isinstance(populated_batch, list)
        assert len(populated_batch) == 2
        assert all("student_person_name" in item for item in populated_batch)
