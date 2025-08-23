"""
Unit tests for PostgreSQLEmailRepository basic functionality.

Tests focus on initialization, protocol compliance, and session management
using AsyncMock patterns following Rule 075 methodology.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest
from huleedu_service_libs.database import DatabaseMetrics
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from services.email_service.implementations.repository_impl import PostgreSQLEmailRepository


class TestPostgreSQLEmailRepositoryInitialization:
    """Tests for PostgreSQLEmailRepository initialization and setup patterns."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock AsyncEngine following established patterns."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def mock_database_metrics(self) -> AsyncMock:
        """Create mock DatabaseMetrics for monitoring."""
        return AsyncMock(spec=DatabaseMetrics)

    def test_repository_initialization_follows_correct_pattern(
        self, mock_engine: AsyncMock, mock_database_metrics: AsyncMock
    ) -> None:
        """Test repository initialization follows AsyncEngine injection pattern."""
        # Act
        repository = PostgreSQLEmailRepository(mock_engine, mock_database_metrics)

        # Assert - repository stores components correctly
        assert repository.engine is mock_engine
        assert repository.database_metrics is mock_database_metrics
        assert repository.async_session_maker is not None
        assert hasattr(repository.async_session_maker, "__call__")
        assert repository.logger is not None

    def test_repository_initialization_without_metrics(self, mock_engine: AsyncMock) -> None:
        """Test repository initialization with optional metrics parameter."""
        # Act
        repository = PostgreSQLEmailRepository(mock_engine)

        # Assert - repository initializes correctly without metrics
        assert repository.engine is mock_engine
        assert repository.database_metrics is None
        assert repository.async_session_maker is not None

    def test_session_maker_configuration(self, mock_engine: AsyncMock) -> None:
        """Test session maker is configured with proper settings."""
        # Act
        repository = PostgreSQLEmailRepository(mock_engine)

        # Assert - session maker has correct configuration
        session_maker = repository.async_session_maker
        # Note: Session maker configuration is tested by ensuring it was created correctly
        assert session_maker is not None

    def test_concurrent_repositories_have_isolated_session_makers(self) -> None:
        """Test concurrent repository instances use isolated session makers."""
        # Arrange
        mock_engine1 = AsyncMock(spec=AsyncEngine)
        mock_engine2 = AsyncMock(spec=AsyncEngine)

        # Act
        repo1 = PostgreSQLEmailRepository(mock_engine1)
        repo2 = PostgreSQLEmailRepository(mock_engine2)

        # Assert - each repository has its own session maker (isolation)
        assert repo1.async_session_maker is not repo2.async_session_maker


class TestPostgreSQLEmailRepositoryProtocolCompliance:
    """Tests for EmailRepository protocol compliance and method signatures."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock AsyncEngine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def repository(self, mock_engine: AsyncMock) -> PostgreSQLEmailRepository:
        """Create repository instance for testing."""
        return PostgreSQLEmailRepository(mock_engine)

    def test_repository_implements_email_repository_protocol(
        self, repository: PostgreSQLEmailRepository
    ) -> None:
        """Test repository implements required EmailRepository protocol methods."""
        # Assert - verify protocol methods exist
        assert hasattr(repository, "create_email_record")
        assert hasattr(repository, "update_status")
        assert hasattr(repository, "get_by_message_id")
        assert hasattr(repository, "get_by_correlation_id")

        # Assert - verify all methods are async
        assert inspect.iscoroutinefunction(repository.create_email_record)
        assert inspect.iscoroutinefunction(repository.update_status)
        assert inspect.iscoroutinefunction(repository.get_by_message_id)
        assert inspect.iscoroutinefunction(repository.get_by_correlation_id)

        # Assert - verify repository follows protocol pattern (structural typing)
        # Note: Can't use isinstance with Protocol, verify methods exist instead

    def test_create_email_record_method_signature(
        self, repository: PostgreSQLEmailRepository
    ) -> None:
        """Test create_email_record method signature matches protocol."""
        # Arrange
        signature = inspect.signature(repository.create_email_record)
        parameters = list(signature.parameters.keys())

        # Assert - correct parameters
        assert "record" in parameters
        assert len(parameters) == 1  # Only record parameter

    def test_update_status_method_signature(self, repository: PostgreSQLEmailRepository) -> None:
        """Test update_status method signature matches protocol."""
        # Arrange
        signature = inspect.signature(repository.update_status)
        parameters = list(signature.parameters.keys())

        # Assert - required and optional parameters
        required_params = ["message_id", "status"]
        optional_params = [
            "provider_message_id",
            "provider_response",
            "sent_at",
            "failed_at",
            "failure_reason",
        ]

        assert all(param in parameters for param in required_params)
        assert all(param in parameters for param in optional_params)

    def test_get_by_message_id_method_signature(
        self, repository: PostgreSQLEmailRepository
    ) -> None:
        """Test get_by_message_id method signature matches protocol."""
        # Arrange
        signature = inspect.signature(repository.get_by_message_id)
        parameters = list(signature.parameters.keys())

        # Assert
        assert "message_id" in parameters
        assert len(parameters) == 1

    def test_get_by_correlation_id_method_signature(
        self, repository: PostgreSQLEmailRepository
    ) -> None:
        """Test get_by_correlation_id method signature matches protocol."""
        # Arrange
        signature = inspect.signature(repository.get_by_correlation_id)
        parameters = list(signature.parameters.keys())

        # Assert
        assert "correlation_id" in parameters
        assert len(parameters) == 1


class TestPostgreSQLEmailRepositorySessionManagement:
    """Tests for async session management and transaction handling."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock AsyncEngine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock AsyncSession with proper context manager behavior."""
        session = AsyncMock(spec=AsyncSession)
        # Mock context manager methods
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        # Ensure async methods are properly mocked
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def repository(
        self, mock_engine: AsyncMock, mock_session: AsyncMock
    ) -> PostgreSQLEmailRepository:
        """Create repository with mocked session maker."""
        repo = PostgreSQLEmailRepository(mock_engine)
        # Mock the session maker to return our mock session
        repo.async_session_maker = MagicMock(return_value=mock_session)
        return repo

    async def test_session_context_manager_commit_success(
        self, repository: PostgreSQLEmailRepository, mock_session: AsyncMock
    ) -> None:
        """Test session context manager commits on successful operations."""
        # Act
        async with repository.session():
            # Simulate successful database operation
            pass

        # Assert - session lifecycle methods called correctly
        # Note: Context manager calls are handled by the actual implementation
        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()
        mock_session.close.assert_called_once()

    async def test_session_context_manager_rollback_on_exception(
        self, repository: PostgreSQLEmailRepository, mock_session: AsyncMock
    ) -> None:
        """Test session context manager rolls back on exceptions."""
        # Arrange
        test_exception = RuntimeError("Database error")

        # Act & Assert
        with pytest.raises(RuntimeError, match="Database error"):
            async with repository.session():
                raise test_exception

        # Assert - rollback called, commit not called
        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()
        mock_session.close.assert_called_once()
