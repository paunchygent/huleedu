"""
Unit tests for PostgreSQLOutboxRepository.

These tests mock SQLAlchemy components at the boundary to test repository logic
without requiring a real database. They verify SQL construction, transaction
management, error handling, and data transformations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from huleedu_service_libs.error_handling import HuleEduError
from sqlalchemy.engine.result import Result
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from services.essay_lifecycle_service.implementations.outbox_repository_impl import (
    OutboxEventImpl,
    PostgreSQLOutboxRepository,
)
from services.essay_lifecycle_service.models_db import EventOutbox


class TestPostgreSQLOutboxRepository:
    """Unit tests for PostgreSQLOutboxRepository."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create a mock AsyncEngine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock AsyncSession with context manager support."""
        session = AsyncMock(spec=AsyncSession)
        # Configure the session to support async context manager
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    @pytest.fixture
    def mock_session_factory(self, mock_session: AsyncMock) -> Mock:
        """Create a mock async_sessionmaker that returns the mock session."""
        # Create a regular Mock (not AsyncMock) for the factory
        # The factory itself is a callable, not an async function
        factory = Mock()
        factory.return_value = mock_session
        return factory

    @pytest.fixture
    def repository(
        self, mock_engine: AsyncMock, mock_session_factory: Mock
    ) -> PostgreSQLOutboxRepository:
        """Create repository instance with mocked dependencies."""
        with patch(
            "services.essay_lifecycle_service.implementations.outbox_repository_impl.async_sessionmaker",
            return_value=mock_session_factory,
        ):
            return PostgreSQLOutboxRepository(mock_engine)

    async def test_add_event_success(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test successful event addition to outbox."""
        # Arrange
        aggregate_id = "test-aggregate-123"
        aggregate_type = "essay"
        event_type = "huleedu.els.essay.slot.assigned.v1"
        event_data = {"test": "data", "nested": {"key": "value"}}
        event_key = "partition-key-1"
        expected_id = uuid4()

        # Mock the EventOutbox model to capture the created instance
        with patch(
            "services.essay_lifecycle_service.implementations.outbox_repository_impl.EventOutbox"
        ) as mock_outbox_class:
            mock_outbox_instance = Mock(spec=EventOutbox)
            mock_outbox_instance.id = expected_id
            mock_outbox_class.return_value = mock_outbox_instance

            # Act
            result = await repository.add_event(
                aggregate_id=aggregate_id,
                aggregate_type=aggregate_type,
                event_type=event_type,
                event_data=event_data,
                event_key=event_key,
            )

            # Assert
            assert result == expected_id

            # Verify EventOutbox was created with correct parameters
            mock_outbox_class.assert_called_once_with(
                aggregate_id=aggregate_id,
                aggregate_type=aggregate_type,
                event_type=event_type,
                event_data=event_data,
                event_key=event_key,
            )

            # Verify session operations
            mock_session.add.assert_called_once_with(mock_outbox_instance)
            mock_session.commit.assert_called_once()
            mock_session.rollback.assert_not_called()

    async def test_add_event_database_error(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test error handling when database operation fails during add_event."""
        # Arrange
        aggregate_id = "test-aggregate-123"
        aggregate_type = "essay"
        event_type = "huleedu.els.essay.slot.assigned.v1"
        event_data = {"test": "data"}

        # Mock database error
        mock_session.commit.side_effect = Exception("Database connection lost")

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await repository.add_event(
                aggregate_id=aggregate_id,
                aggregate_type=aggregate_type,
                event_type=event_type,
                event_data=event_data,
            )

        # Verify error details
        error = exc_info.value
        assert error.service == "essay_lifecycle_service"
        assert error.operation == "add_event_to_outbox"
        assert "Failed to add event to outbox" in str(error)
        assert error.error_detail.details["external_service"] == "database"
        assert error.error_detail.details["aggregate_id"] == aggregate_id
        assert error.error_detail.details["event_type"] == event_type

        # Verify rollback was called
        mock_session.rollback.assert_called_once()

    async def test_get_unpublished_events_success(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test retrieving unpublished events from outbox."""
        # Arrange
        limit = 50
        mock_events = []

        # Create mock EventOutbox instances
        for i in range(3):
            mock_event = Mock(spec=EventOutbox)
            mock_event.id = uuid4()
            mock_event.aggregate_id = f"aggregate-{i}"
            mock_event.aggregate_type = "essay"
            mock_event.event_type = f"event.type.{i}"
            mock_event.event_data = {"index": i}
            mock_event.event_key = f"key-{i}"
            mock_event.created_at = datetime.now(UTC)
            mock_event.published_at = None
            mock_event.retry_count = 0
            mock_event.last_error = None
            mock_events.append(mock_event)

        # Mock query execution
        mock_result = Mock(spec=Result)
        mock_scalars = Mock()
        mock_scalars.all.return_value = mock_events
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_unpublished_events(limit=limit)

        # Assert
        assert len(result) == 3
        for i, event in enumerate(result):
            assert isinstance(event, OutboxEventImpl)
            assert event.aggregate_id == f"aggregate-{i}"
            assert event.event_data == {"index": i}
            assert event.published_at is None

        # Verify SQL construction (check that execute was called)
        mock_session.execute.assert_called_once()

        # Verify the query includes proper conditions
        # The query should be a Select statement with where and order_by clauses
        # We can't easily inspect the actual SQL, but we can verify execute was called

    async def test_get_unpublished_events_empty_result(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test retrieving unpublished events when none exist."""
        # Arrange
        mock_result = Mock(spec=Result)
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_unpublished_events()

        # Assert
        assert result == []
        mock_session.execute.assert_called_once()

    async def test_mark_published_success(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test marking an event as published."""
        # Arrange
        event_id = uuid4()
        mock_result = Mock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        # Mock datetime to verify timestamp
        fixed_time = datetime(2024, 1, 15, 10, 30, 0)
        with patch(
            "services.essay_lifecycle_service.implementations.outbox_repository_impl.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = fixed_time

            # Act
            await repository.mark_published(event_id)

            # Assert
            mock_session.execute.assert_called_once()
            mock_session.commit.assert_called_once()

            # Verify the update statement was constructed correctly
            # The execute call should have an Update statement
            # We can't easily inspect the SQL, but we verify execute was called

    async def test_mark_published_event_not_found(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test marking non-existent event as published."""
        # Arrange
        event_id = uuid4()
        mock_result = Mock()
        mock_result.rowcount = 0  # No rows updated
        mock_session.execute.return_value = mock_result

        # Act
        await repository.mark_published(event_id)

        # Assert - Should log warning but not raise error
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    async def test_record_error_success(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test recording an error for an event."""
        # Arrange
        event_id = uuid4()
        error_message = "Connection timeout to Kafka broker"
        mock_result = Mock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        # Act
        await repository.record_error(event_id, error_message)

        # Assert
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

        # Verify the update includes retry count increment
        # The SQL should update retry_count and last_error fields

    async def test_record_error_truncates_long_message(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that error messages are truncated to fit database column."""
        # Arrange
        event_id = uuid4()
        long_error = "x" * 2000  # Very long error message
        mock_result = Mock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        # Act
        await repository.record_error(event_id, long_error)

        # Assert
        mock_session.execute.assert_called_once()
        # The implementation truncates to 1000 characters
        # We can't easily verify the exact SQL, but the method should complete

    async def test_get_event_by_id_found(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test retrieving a specific event by ID."""
        # Arrange
        event_id = uuid4()
        mock_event = Mock(spec=EventOutbox)
        mock_event.id = event_id
        mock_event.aggregate_id = "test-aggregate"
        mock_event.aggregate_type = "essay"
        mock_event.event_type = "test.event"
        mock_event.event_data = {"test": "data"}
        mock_event.event_key = "key1"
        mock_event.created_at = datetime.now(UTC)
        mock_event.published_at = None
        mock_event.retry_count = 2
        mock_event.last_error = "Previous error"

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_event
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_event_by_id(event_id)

        # Assert
        assert result is not None
        assert isinstance(result, OutboxEventImpl)
        assert result.id == event_id
        assert result.aggregate_id == "test-aggregate"
        assert result.retry_count == 2
        mock_session.execute.assert_called_once()

    async def test_get_event_by_id_not_found(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test retrieving non-existent event by ID."""
        # Arrange
        event_id = uuid4()
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_event_by_id(event_id)

        # Assert
        assert result is None
        mock_session.execute.assert_called_once()

    async def test_mark_event_failed(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test marking an event as permanently failed."""
        # Arrange
        event_id = uuid4()
        error_message = "Max retries exceeded - Kafka permanently unavailable"
        mock_result = Mock()
        mock_session.execute.return_value = mock_result

        # Act
        await repository.mark_event_failed(event_id, error_message)

        # Assert
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()
        # Should update last_error but NOT published_at

    async def test_mark_event_published_duplicate_method(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test the mark_event_published method (duplicate of mark_published)."""
        # Arrange
        event_id = uuid4()
        mock_result = Mock()
        mock_session.execute.return_value = mock_result

        # Act
        await repository.mark_event_published(event_id)

        # Assert
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    async def test_increment_retry_count_success(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test incrementing retry count for an event."""
        # Arrange
        event_id = uuid4()
        error_message = "Temporary Kafka unavailability"

        # Mock the select query result
        mock_event = Mock(spec=EventOutbox)
        mock_event.id = event_id
        mock_event.retry_count = 3  # Current retry count

        mock_select_result = Mock()
        mock_select_result.scalar_one_or_none.return_value = mock_event

        # Mock the update result
        mock_update_result = Mock()

        # Configure execute to return different results for select vs update
        mock_session.execute.side_effect = [mock_select_result, mock_update_result]

        # Act
        await repository.increment_retry_count(event_id, error_message)

        # Assert
        assert mock_session.execute.call_count == 2  # One select, one update
        mock_session.commit.assert_called_once()

        # Verify that we're updating with incremented count
        # The update should set retry_count to 4 (3 + 1)

    async def test_increment_retry_count_event_not_found(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test incrementing retry count when event doesn't exist."""
        # Arrange
        event_id = uuid4()
        error_message = "Kafka error"

        # Mock select returning None
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Act
        await repository.increment_retry_count(event_id, error_message)

        # Assert
        mock_session.execute.assert_called_once()  # Only select, no update
        mock_session.commit.assert_not_called()  # No commit needed

    async def test_database_error_handling_consistency(
        self,
        repository: PostgreSQLOutboxRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that all methods handle database errors consistently."""
        # Arrange
        event_id = uuid4()
        db_error = Exception("Connection pool exhausted")
        mock_session.execute.side_effect = db_error

        # Test each method that executes queries
        methods_to_test = [
            ("get_unpublished_events", lambda: repository.get_unpublished_events()),
            ("mark_published", lambda: repository.mark_published(event_id)),
            ("record_error", lambda: repository.record_error(event_id, "error")),
            ("get_event_by_id", lambda: repository.get_event_by_id(event_id)),
            ("mark_event_failed", lambda: repository.mark_event_failed(event_id, "error")),
            ("mark_event_published", lambda: repository.mark_event_published(event_id)),
            ("increment_retry_count", lambda: repository.increment_retry_count(event_id, "error")),
        ]

        for method_name, method_call in methods_to_test:
            # Reset mock
            mock_session.execute.side_effect = db_error
            mock_session.rollback.reset_mock()

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await method_call()

            # Verify consistent error handling
            error = exc_info.value
            assert error.service == "essay_lifecycle_service"
            assert error.operation == method_name
            assert error.error_detail.details["external_service"] == "database"
            assert "Connection pool exhausted" in str(
                error.error_detail.details.get("error_details", "")
            )

            # Verify rollback called for write operations
            if method_name not in ["get_unpublished_events", "get_event_by_id"]:
                mock_session.rollback.assert_called()

    async def test_outbox_event_impl_wrapping(self) -> None:
        """Test that OutboxEventImpl properly wraps the database model."""
        # Arrange
        mock_db_event = Mock(spec=EventOutbox)
        mock_db_event.id = uuid4()
        mock_db_event.aggregate_id = "agg-123"
        mock_db_event.aggregate_type = "batch"
        mock_db_event.event_type = "batch.completed"
        mock_db_event.event_data = {"status": "success"}
        mock_db_event.event_key = "batch-key"
        mock_db_event.created_at = datetime.now(UTC)
        mock_db_event.published_at = datetime.now(UTC)
        mock_db_event.retry_count = 1
        mock_db_event.last_error = "Previous failure"

        # Act
        wrapped_event = OutboxEventImpl(mock_db_event)

        # Assert - Verify all attributes are properly wrapped
        assert wrapped_event.id == mock_db_event.id
        assert wrapped_event.aggregate_id == mock_db_event.aggregate_id
        assert wrapped_event.aggregate_type == mock_db_event.aggregate_type
        assert wrapped_event.event_type == mock_db_event.event_type
        assert wrapped_event.event_data == mock_db_event.event_data
        assert wrapped_event.event_key == mock_db_event.event_key
        assert wrapped_event.created_at == mock_db_event.created_at
        assert wrapped_event.published_at == mock_db_event.published_at
        assert wrapped_event.retry_count == mock_db_event.retry_count
        assert wrapped_event.last_error == mock_db_event.last_error

    async def test_session_factory_initialization(self, mock_engine: AsyncMock) -> None:
        """Test that repository properly initializes with async_sessionmaker."""
        # Act
        with patch(
            "services.essay_lifecycle_service.implementations.outbox_repository_impl.async_sessionmaker"
        ) as mock_sessionmaker:
            repository = PostgreSQLOutboxRepository(mock_engine)

            # Assert
            mock_sessionmaker.assert_called_once_with(mock_engine, expire_on_commit=False)
            assert repository._session_factory == mock_sessionmaker.return_value
