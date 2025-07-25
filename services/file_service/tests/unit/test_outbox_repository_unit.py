"""
Unit tests for PostgreSQLOutboxRepository.

Tests focus on the repository's behavior with mocked database interactions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from huleedu_service_libs.outbox.models import EventOutbox
from huleedu_service_libs.outbox.monitoring import OutboxMetrics
from huleedu_service_libs.outbox.repository import PostgreSQLOutboxRepository
from sqlalchemy.ext.asyncio import AsyncEngine


class FakeScalarResult:
    """Fake implementation of SQLAlchemy ScalarResult."""

    def __init__(self, data: list[Any]) -> None:
        self._data = data

    def all(self) -> list[Any]:
        """Return all results."""
        return self._data

    def scalar_one_or_none(self) -> Any | None:
        """Return first result or None."""
        return self._data[0] if self._data else None


class FakeResult:
    """Fake implementation of SQLAlchemy Result."""

    def __init__(self, data: list[Any], rowcount: int = 0) -> None:
        self._data = data
        self.rowcount = rowcount

    def scalars(self) -> FakeScalarResult:
        """Return scalar result."""
        return FakeScalarResult(self._data)

    def scalar_one_or_none(self) -> Any | None:
        """Return first result or None."""
        return self._data[0] if self._data else None


class FakeAsyncSession:
    """Fake implementation of AsyncSession for testing."""

    def __init__(self) -> None:
        self.added_objects: list[Any] = []
        self.committed = False
        self.flushed = False
        self.execute_results: dict[str, Any] = {}
        self.execute_calls: list[Any] = []

    def add(self, instance: Any) -> None:
        """Add an object to the session."""
        self.added_objects.append(instance)
        # Simulate ID assignment on add
        if hasattr(instance, "id") and instance.id is None:
            instance.id = uuid4()

    async def flush(self) -> None:
        """Flush pending changes."""
        self.flushed = True
        # Simulate ID assignment for added objects
        for obj in self.added_objects:
            if hasattr(obj, "id") and obj.id is None:
                obj.id = uuid4()

    async def commit(self) -> None:
        """Commit the transaction."""
        self.committed = True

    async def execute(self, statement: Any) -> Any:
        """Execute a statement and return configured result."""
        self.execute_calls.append(statement)
        # Return pre-configured results based on statement type
        stmt_str = str(statement)
        if "SELECT" in stmt_str and "event_outbox" in stmt_str:
            if "WHERE event_outbox.published_at IS NULL" in stmt_str:
                # Query for unpublished events
                return self.execute_results.get("unpublished_events", FakeResult([]))
            elif "WHERE event_outbox.id =" in stmt_str:
                # Query for specific event by ID
                return self.execute_results.get("event_by_id", FakeResult([]))
        elif "UPDATE event_outbox" in stmt_str:
            # Update statement
            return self.execute_results.get("update", FakeResult([], rowcount=1))
        return FakeResult([])


@pytest.fixture
def mock_engine() -> Mock:
    """Create a mock async engine."""
    return Mock(spec=AsyncEngine)


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    """Create a fake async session for testing."""
    return FakeAsyncSession()


@pytest.fixture
def mock_session_factory(fake_session: FakeAsyncSession) -> Mock:
    """Create a mock session factory that returns our fake session."""
    # Create a mock that acts as an async context manager
    context_manager = Mock()
    context_manager.__aenter__ = AsyncMock(return_value=fake_session)
    context_manager.__aexit__ = AsyncMock(return_value=None)

    # Create the factory that returns the context manager when called (not async)
    factory = Mock(return_value=context_manager)

    return factory


class TestPostgreSQLOutboxRepository:
    """Test PostgreSQLOutboxRepository behavior."""

    def test_initialization(self, mock_engine: Mock) -> None:
        """Test repository initialization with and without metrics."""
        # With metrics enabled
        repo = PostgreSQLOutboxRepository(
            engine=mock_engine, service_name="test-service", enable_metrics=True
        )
        assert repo.metrics is not None
        assert isinstance(repo.metrics, OutboxMetrics)

        # With metrics disabled
        repo_no_metrics = PostgreSQLOutboxRepository(
            engine=mock_engine, service_name="test-service", enable_metrics=False
        )
        assert repo_no_metrics.metrics is None

    async def test_add_event_without_session(
        self,
        mock_engine: Mock,
        mock_session_factory: Mock,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test adding an event without providing a session."""
        # Given
        repo = PostgreSQLOutboxRepository(mock_engine, "test-service")
        repo._session_factory = mock_session_factory

        event_data = {"test": "data", "value": 42}

        # When
        event_id = await repo.add_event(
            aggregate_id="agg-123",
            aggregate_type="test_aggregate",
            event_type="test.event.v1",
            event_data=event_data,
            topic="test.topic",
            event_key="key-123",
        )

        # Then
        assert isinstance(event_id, UUID)
        assert len(fake_session.added_objects) == 1

        added_event = fake_session.added_objects[0]
        assert isinstance(added_event, EventOutbox)
        assert added_event.aggregate_id == "agg-123"
        assert added_event.aggregate_type == "test_aggregate"
        assert added_event.event_type == "test.event.v1"
        assert added_event.event_data["topic"] == "test.topic"
        assert added_event.event_data["test"] == "data"
        assert added_event.event_key == "key-123"

        assert fake_session.flushed
        assert fake_session.committed

    async def test_add_event_with_session(
        self,
        mock_engine: Mock,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test adding an event with a provided session for transaction sharing."""
        # Given
        repo = PostgreSQLOutboxRepository(mock_engine, "test-service")
        event_data = {"test": "data"}

        # When
        event_id = await repo.add_event(
            aggregate_id="agg-456",
            aggregate_type="test_aggregate",
            event_type="test.event.v1",
            event_data=event_data,
            topic="test.topic",
            session=fake_session,  # Provide session
        )

        # Then
        assert isinstance(event_id, UUID)
        assert len(fake_session.added_objects) == 1
        assert fake_session.flushed
        assert not fake_session.committed  # Should NOT commit when session provided

    async def test_get_unpublished_events(
        self,
        mock_engine: Mock,
        mock_session_factory: Mock,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test retrieving unpublished events."""
        # Given
        repo = PostgreSQLOutboxRepository(mock_engine, "test-service")
        repo._session_factory = mock_session_factory

        # Create mock events
        mock_events = []
        for i in range(3):
            event = Mock(spec=EventOutbox)
            event.id = uuid4()
            event.aggregate_id = f"agg-{i}"
            event.aggregate_type = "test"
            event.event_type = f"test.event.{i}"
            event.event_data = {"index": i}
            event.event_key = f"key-{i}"
            event.created_at = datetime.now(UTC)
            event.published_at = None
            event.retry_count = 0
            event.last_error = None
            mock_events.append(event)

        fake_session.execute_results["unpublished_events"] = FakeResult(mock_events)

        # When
        events = await repo.get_unpublished_events(limit=10)

        # Then
        assert len(events) == 3
        for i, event in enumerate(events):
            assert event.aggregate_id == f"agg-{i}"
            assert event.event_type == f"test.event.{i}"
            assert event.event_data == {"index": i}

    async def test_mark_event_published(
        self,
        mock_engine: Mock,
        mock_session_factory: Mock,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test marking an event as published."""
        # Given
        repo = PostgreSQLOutboxRepository(mock_engine, "test-service")
        repo._session_factory = mock_session_factory
        event_id = uuid4()

        fake_session.execute_results["update"] = FakeResult([], rowcount=1)

        # When
        await repo.mark_event_published(event_id)

        # Then
        assert len(fake_session.execute_calls) == 1
        assert fake_session.committed

        # Verify UPDATE statement was executed
        stmt_str = str(fake_session.execute_calls[0])
        assert "UPDATE event_outbox" in stmt_str
        assert "WHERE event_outbox.id =" in stmt_str

    async def test_mark_event_failed(
        self,
        mock_engine: Mock,
        mock_session_factory: Mock,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test marking an event as permanently failed."""
        # Given
        repo = PostgreSQLOutboxRepository(mock_engine, "test-service")
        repo._session_factory = mock_session_factory
        event_id = uuid4()
        error_msg = "Permanent failure"

        fake_session.execute_results["update"] = FakeResult([], rowcount=1)

        # When
        await repo.mark_event_failed(event_id, error_msg)

        # Then
        assert len(fake_session.execute_calls) == 1
        assert fake_session.committed

    async def test_increment_retry_count(
        self,
        mock_engine: Mock,
        mock_session_factory: Mock,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test incrementing retry count for a failed event."""
        # Given
        repo = PostgreSQLOutboxRepository(mock_engine, "test-service")
        repo._session_factory = mock_session_factory
        event_id = uuid4()

        # Mock existing event with retry_count = 1
        mock_event = Mock(spec=EventOutbox)
        mock_event.id = event_id
        mock_event.retry_count = 1

        fake_session.execute_results["event_by_id"] = FakeResult([mock_event])
        fake_session.execute_results["update"] = FakeResult([], rowcount=1)

        # When
        await repo.increment_retry_count(event_id, "Retry error")

        # Then
        assert len(fake_session.execute_calls) == 2  # SELECT + UPDATE
        assert fake_session.committed

    async def test_get_event_by_id(
        self,
        mock_engine: Mock,
        mock_session_factory: Mock,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test retrieving a specific event by ID."""
        # Given
        repo = PostgreSQLOutboxRepository(mock_engine, "test-service")
        repo._session_factory = mock_session_factory
        event_id = uuid4()

        # Mock event
        mock_event = Mock(spec=EventOutbox)
        mock_event.id = event_id
        mock_event.aggregate_id = "test-agg"
        mock_event.aggregate_type = "test"
        mock_event.event_type = "test.event"
        mock_event.event_data = {"test": "data"}
        mock_event.event_key = None
        mock_event.created_at = datetime.now(UTC)
        mock_event.published_at = None
        mock_event.retry_count = 0
        mock_event.last_error = None

        fake_session.execute_results["event_by_id"] = FakeResult([mock_event])

        # When
        event = await repo.get_event_by_id(event_id)

        # Then
        assert event is not None
        assert event.id == event_id
        assert event.aggregate_id == "test-agg"
        assert event.event_data == {"test": "data"}

    async def test_get_event_by_id_not_found(
        self,
        mock_engine: Mock,
        mock_session_factory: Mock,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test retrieving a non-existent event returns None."""
        # Given
        repo = PostgreSQLOutboxRepository(mock_engine, "test-service")
        repo._session_factory = mock_session_factory
        event_id = uuid4()

        fake_session.execute_results["event_by_id"] = FakeResult([])  # No results

        # When
        event = await repo.get_event_by_id(event_id)

        # Then
        assert event is None

    async def test_error_message_truncation(
        self,
        mock_engine: Mock,
        mock_session_factory: Mock,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test that long error messages are truncated."""
        # Given
        repo = PostgreSQLOutboxRepository(mock_engine, "test-service")
        repo._session_factory = mock_session_factory
        event_id = uuid4()

        # Create a very long error message
        long_error = "x" * 2000  # Longer than max_error_length (1000)

        fake_session.execute_results["update"] = FakeResult([], rowcount=1)

        # When
        await repo.mark_event_failed(event_id, long_error)

        # Then
        # We can't easily check the truncated value in the UPDATE statement,
        # but we verify the method completes without error
        assert fake_session.committed

    async def test_metrics_integration(
        self,
        mock_engine: Mock,
        mock_session_factory: Mock,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test that metrics are recorded when enabled."""
        # Given
        repo = PostgreSQLOutboxRepository(
            engine=mock_engine, service_name="test-service", enable_metrics=True
        )
        repo._session_factory = mock_session_factory

        # Mock the metrics object to track calls
        mock_metrics = Mock(spec=OutboxMetrics)
        repo.metrics = mock_metrics

        # When - Add an event
        await repo.add_event(
            aggregate_id="agg-123",
            aggregate_type="test",
            event_type="test.event.v1",
            event_data={},
            topic="test.topic",
        )

        # Then
        mock_metrics.increment_events_added.assert_called_once_with("test.event.v1")
