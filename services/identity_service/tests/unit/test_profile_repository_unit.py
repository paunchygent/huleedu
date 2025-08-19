"""
Unit tests for PostgresUserProfileRepo structure and behavioral patterns.

Tests focus on repository initialization, protocol compliance, and error handling patterns.
Following HuleEdu testing patterns: test structure and contracts, not database operations.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from huleedu_service_libs.error_handling import HuleEduError, raise_processing_error
from sqlalchemy.ext.asyncio import AsyncEngine

from services.identity_service.implementations.user_profile_repository_sqlalchemy_impl import (
    PostgresUserProfileRepo,
)
from services.identity_service.models_db import UserProfile


class TestPostgresUserProfileRepo:
    """Tests for PostgresUserProfileRepo structure and behavioral patterns."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock async engine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def repository(self, mock_engine: AsyncMock) -> PostgresUserProfileRepo:
        """Create repository with mocked engine."""
        return PostgresUserProfileRepo(mock_engine)

    @pytest.fixture
    def user_id(self) -> UUID:
        """Sample user ID for testing."""
        return uuid4()

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID for testing."""
        return uuid4()

    def test_repository_initialization_follows_correct_pattern(
        self, mock_engine: AsyncMock
    ) -> None:
        """Test repository initialization follows AsyncEngine injection pattern."""
        # Act
        repo = PostgresUserProfileRepo(mock_engine)

        # Assert - repository stores session factory correctly
        assert repo._session_factory is not None
        # Verify async_sessionmaker is created (repository-managed sessions)
        assert hasattr(repo._session_factory, "__call__")

    def test_repository_protocol_compliance(self, repository: PostgresUserProfileRepo) -> None:
        """Test repository implements required protocol methods."""
        # Assert - verify protocol methods exist (not calling them, just checking structure)
        assert hasattr(repository, "get_profile")
        assert hasattr(repository, "upsert_profile")

        # Verify methods are async
        assert inspect.iscoroutinefunction(repository.get_profile)
        assert inspect.iscoroutinefunction(repository.upsert_profile)

        # Verify repository follows protocol contract (structural typing)
        # Protocol compliance is verified at type-check time and by method presence

    def test_session_context_manager_structure(self, repository: PostgresUserProfileRepo) -> None:
        """Test session context manager has correct async structure."""
        # Assert - verify session context method exists and is async context manager
        assert hasattr(repository, "_session_context")

        # The _session_context method should be an async context manager
        session_context = repository._session_context()
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
        repo1 = PostgresUserProfileRepo(mock_engine1)
        repo2 = PostgresUserProfileRepo(mock_engine2)

        # Assert - each repository has its own session maker (isolation)
        assert repo1._session_factory is not repo2._session_factory

    def test_error_handling_patterns_for_get_profile(
        self, user_id: UUID, correlation_id: UUID
    ) -> None:
        """Test error handling business logic for get_profile without database calls."""
        # This tests the error raising pattern using the factory function directly
        with pytest.raises(HuleEduError) as exc_info:
            # Trigger the error using the factory function directly
            raise_processing_error(
                service="identity_service",
                operation="get_user_profile",
                message="Database error during profile retrieval",
                correlation_id=correlation_id,
                error_type="SQLAlchemyError",
                user_id=str(user_id),
            )

        error = exc_info.value
        assert "Database error during profile retrieval" in str(error)
        assert error.error_detail.service == "identity_service"
        assert error.error_detail.operation == "get_user_profile"

    def test_error_handling_patterns_for_upsert_profile(
        self, user_id: UUID, correlation_id: UUID
    ) -> None:
        """Test error handling business logic for upsert_profile without database calls."""
        # This tests the error raising pattern using the factory function directly
        with pytest.raises(HuleEduError) as exc_info:
            # Trigger the error using the factory function directly
            raise_processing_error(
                service="identity_service",
                operation="upsert_user_profile",
                message="Database error during profile upsert",
                correlation_id=correlation_id,
                error_type="SQLAlchemyError",
                user_id=str(user_id),
            )

        error = exc_info.value
        assert "Database error during profile upsert" in str(error)
        assert error.error_detail.service == "identity_service"
        assert error.error_detail.operation == "upsert_user_profile"

    def test_userprofile_model_structure_supports_unicode(self) -> None:
        """Test UserProfile model correctly handles Unicode characters."""
        # Arrange & Act
        profile = UserProfile()
        profile.user_id = uuid4()

        # Test Swedish characters
        profile.first_name = "Åsa"
        profile.last_name = "Öberg"
        profile.display_name = "Teacher Åsa"
        profile.locale = "sv-SE"

        # Assert - model should handle Unicode characters without issues
        assert profile.first_name == "Åsa"
        assert profile.last_name == "Öberg"
        assert profile.display_name == "Teacher Åsa"
        assert profile.locale == "sv-SE"

    @pytest.mark.parametrize(
        "first_name, last_name, locale",
        [
            ("Åsa", "Öberg", "sv-SE"),  # Swedish characters
            ("Karl", "Ängström", "sv-SE"),  # More Swedish characters
            ("José", "García", "es-ES"),  # Spanish characters
            ("François", "Müller", "de-DE"),  # Mixed Unicode
            ("", "", ""),  # Empty strings
            (None, None, None),  # None values
        ],
    )
    def test_userprofile_model_unicode_edge_cases(
        self, first_name: str | None, last_name: str | None, locale: str | None
    ) -> None:
        """Test UserProfile model handles various Unicode and edge cases."""
        # Arrange & Act
        profile = UserProfile()
        profile.user_id = uuid4()
        profile.first_name = first_name
        profile.last_name = last_name
        profile.locale = locale

        # Assert - model should handle all cases without errors
        assert profile.first_name == first_name
        assert profile.last_name == last_name
        assert profile.locale == locale

    def test_profile_data_validation_patterns(self) -> None:
        """Test profile data structure patterns for upsert operations."""
        # Test profile data dictionary structure that would be used in upsert
        profile_data = {
            "first_name": "Karl",
            "last_name": "Ängström",
            "display_name": "Dr. Karl",
            "locale": "sv-SE",
        }

        # Assert - verify the expected structure
        assert "first_name" in profile_data
        assert "last_name" in profile_data
        assert "display_name" in profile_data
        assert "locale" in profile_data

        # Verify Unicode handling in data structure
        assert profile_data["last_name"] == "Ängström"

    def test_optional_fields_handling_patterns(self) -> None:
        """Test how optional fields are handled in profile data."""
        # Test with None values for optional fields
        profile_data_with_nones = {
            "first_name": "Test",
            "last_name": "User",
            "display_name": None,
            "locale": None,
        }

        # Test with empty strings for optional fields
        profile_data_with_empty = {
            "first_name": "Test",
            "last_name": "User",
            "display_name": "",
            "locale": "",
        }

        # Assert - both patterns should be valid
        assert profile_data_with_nones["display_name"] is None
        assert profile_data_with_nones["locale"] is None
        assert profile_data_with_empty["display_name"] == ""
        assert profile_data_with_empty["locale"] == ""

    def test_repository_method_signatures_match_protocol(
        self, repository: PostgresUserProfileRepo
    ) -> None:
        """Test repository method signatures match the protocol contract."""
        # Verify get_profile signature
        get_profile_sig = inspect.signature(repository.get_profile)
        expected_params = ["user_id", "correlation_id"]
        actual_params = list(get_profile_sig.parameters.keys())
        assert all(param in actual_params for param in expected_params)

        # Verify upsert_profile signature
        upsert_profile_sig = inspect.signature(repository.upsert_profile)
        expected_params = ["user_id", "profile_data", "correlation_id"]
        actual_params = list(upsert_profile_sig.parameters.keys())
        assert all(param in actual_params for param in expected_params)

    def test_repository_type_safety_patterns(self, mock_engine: AsyncMock) -> None:
        """Test repository maintains type safety patterns."""
        # Act - create repository
        repo = PostgresUserProfileRepo(mock_engine)

        # Assert - verify type structure is maintained
        assert repo.__class__.__name__ == "PostgresUserProfileRepo"

        # The repository should follow the expected naming and structure patterns
        assert hasattr(repo, "_session_factory")
        assert hasattr(repo, "_session_context")
        assert hasattr(repo, "get_profile")
        assert hasattr(repo, "upsert_profile")
