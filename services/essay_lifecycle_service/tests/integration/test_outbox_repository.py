"""
Integration tests for OutboxRepository implementation.
# IMPORTANT: This is an integration test that requires PostgreSQL.
# It tests the actual repository implementation against a real database.

Tests transactional outbox repository functionality including:
- Event insertion
- Event retrieval for publishing
- Marking events as published
- Retry count tracking
- Error handling
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.essay_lifecycle_service.implementations.outbox_repository_impl import (
    PostgreSQLOutboxRepository,
)
from services.essay_lifecycle_service.models_db import Base


class TestOutboxRepository:
    """Integration tests for PostgreSQL OutboxRepository implementation."""

    @pytest.fixture(autouse=True)
    async def clean_database(self, test_engine: AsyncEngine) -> AsyncIterator[None]:
        """Clean database before each test to ensure isolation."""
        async with test_engine.begin() as conn:
            # Truncate the event_outbox table before each test
            await conn.execute(text("TRUNCATE TABLE event_outbox CASCADE"))
        yield

    @pytest.fixture(scope="class")
    def postgres_container(self) -> Generator[PostgresContainer, Any, None]:
        """Start PostgreSQL test container for integration tests."""
        container = PostgresContainer("postgres:15")
        container.start()
        yield container
        container.stop()

    @pytest.fixture
    async def test_engine(
        self, postgres_container: PostgresContainer
    ) -> AsyncIterator[AsyncEngine]:
        """Create PostgreSQL engine connected to test container."""
        # Get connection URL and ensure it uses asyncpg driver
        connection_url = postgres_container.get_connection_url()
        # Testcontainers returns psycopg2 URLs, we need asyncpg
        # Handle both psycopg2 and plain postgresql URLs
        if "psycopg2" in connection_url:
            async_url = connection_url.replace("psycopg2", "asyncpg")
        else:
            # Replace only the first occurrence to avoid double replacement
            parts = connection_url.split("://", 1)
            if len(parts) == 2 and parts[0] == "postgresql":
                async_url = f"postgresql+asyncpg://{parts[1]}"
            else:
                async_url = connection_url

        # Create engine and initialize schema
        engine = create_async_engine(async_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield engine
        await engine.dispose()

    @pytest.fixture
    def repository(self, test_engine: AsyncEngine) -> PostgreSQLOutboxRepository:
        """Create repository instance with test engine."""
        return PostgreSQLOutboxRepository(test_engine)

    async def test_add_event_success(self, repository: PostgreSQLOutboxRepository) -> None:
        """Test successful event addition to outbox."""
        # Arrange
        aggregate_id = str(uuid4())
        event_type = "test.event.created.v1"
        event_data = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "data": {"test": "value"},
            "metadata": {},
        }

        # Act
        await repository.add_event(
            aggregate_id=aggregate_id,
            aggregate_type="test_aggregate",
            event_type=event_type,
            event_data=event_data,
            event_key=aggregate_id,
        )

        # Assert - verify event was stored
        unpublished = await repository.get_unpublished_events(limit=10)
        assert len(unpublished) == 1
        event = unpublished[0]
        assert event.aggregate_id == aggregate_id
        assert event.event_type == event_type
        # event_data is stored as JSONB in PostgreSQL, so it's already a dict
        assert event.event_data == event_data
        assert event.published_at is None
        assert event.retry_count == 0

    async def test_get_unpublished_events_respects_limit(
        self, repository: PostgreSQLOutboxRepository
    ) -> None:
        """Test that get_unpublished_events respects the limit parameter."""
        # Arrange - add 5 events
        for i in range(5):
            await repository.add_event(
                aggregate_id=str(uuid4()),
                aggregate_type="test",
                event_type=f"test.event.{i}",
                event_data={"index": i},
                event_key=str(uuid4()),
            )

        # Act - request only 3
        events = await repository.get_unpublished_events(limit=3)

        # Assert
        assert len(events) == 3

    async def test_get_unpublished_events_excludes_published(
        self, repository: PostgreSQLOutboxRepository
    ) -> None:
        """Test that published events are not returned."""
        # Arrange - add 3 events
        event_ids = []
        for i in range(3):
            event_id = uuid4()
            event_ids.append(event_id)
            await repository.add_event(
                aggregate_id=str(uuid4()),
                aggregate_type="test",
                event_type="test.event",
                event_data={"index": i},
                event_key=str(uuid4()),
            )

        # Get all events to find their IDs
        all_events = await repository.get_unpublished_events(limit=10)

        # Mark first event as published
        await repository.mark_event_published(all_events[0].id)

        # Act
        unpublished = await repository.get_unpublished_events(limit=10)

        # Assert
        assert len(unpublished) == 2
        assert all(event.published_at is None for event in unpublished)

    async def test_mark_event_published(self, repository: PostgreSQLOutboxRepository) -> None:
        """Test marking an event as published."""
        # Arrange
        await repository.add_event(
            aggregate_id=str(uuid4()),
            aggregate_type="test",
            event_type="test.event",
            event_data={"test": "data"},
            event_key=str(uuid4()),
        )
        events = await repository.get_unpublished_events(limit=1)
        event = events[0]

        # Act
        await repository.mark_event_published(event.id)

        # Assert
        unpublished = await repository.get_unpublished_events(limit=10)
        assert len(unpublished) == 0

    async def test_mark_event_failed(self, repository: PostgreSQLOutboxRepository) -> None:
        """Test marking an event as failed with error message."""
        # Arrange
        await repository.add_event(
            aggregate_id=str(uuid4()),
            aggregate_type="test",
            event_type="test.event",
            event_data={"test": "data"},
            event_key=str(uuid4()),
        )
        events = await repository.get_unpublished_events(limit=1)
        event = events[0]
        error_message = "Connection timeout"

        # Act
        await repository.mark_event_failed(event.id, error_message)

        # Assert - event should still be unpublished but with error
        unpublished = await repository.get_unpublished_events(limit=10)
        assert len(unpublished) == 1
        assert unpublished[0].last_error == error_message

    async def test_increment_retry_count(self, repository: PostgreSQLOutboxRepository) -> None:
        """Test incrementing retry count for an event."""
        # Arrange
        await repository.add_event(
            aggregate_id=str(uuid4()),
            aggregate_type="test",
            event_type="test.event",
            event_data={"test": "data"},
            event_key=str(uuid4()),
        )
        events = await repository.get_unpublished_events(limit=1)
        event = events[0]

        # Act
        await repository.increment_retry_count(event.id, "Test retry 1")
        await repository.increment_retry_count(event.id, "Test retry 2")

        # Assert
        updated_events = await repository.get_unpublished_events(limit=1)
        assert updated_events[0].retry_count == 2

    async def test_get_unpublished_events_orders_by_created_at(
        self, repository: PostgreSQLOutboxRepository
    ) -> None:
        """Test that events are returned in FIFO order."""
        # Arrange - add events with specific order
        event_data = []
        for i in range(3):
            data = {"index": i, "created": str(datetime.now(UTC))}
            event_data.append(data)
            await repository.add_event(
                aggregate_id=str(uuid4()),
                aggregate_type="test",
                event_type="test.event",
                event_data=data,
                event_key=str(uuid4()),
            )

        # Act
        events = await repository.get_unpublished_events(limit=10)

        # Assert - verify FIFO order
        for i, event in enumerate(events):
            # event_data is already a dict when using JSONB
            data = event.event_data
            assert data["index"] == i

    async def test_concurrent_event_additions(self, repository: PostgreSQLOutboxRepository) -> None:
        """Test that concurrent event additions work correctly."""
        import asyncio

        # Arrange
        async def add_event(index: int) -> None:
            await repository.add_event(
                aggregate_id=str(uuid4()),
                aggregate_type="test",
                event_type="test.concurrent",
                event_data={"index": index},
                event_key=str(uuid4()),
            )

        # Act - add 10 events concurrently
        await asyncio.gather(*[add_event(i) for i in range(10)])

        # Assert
        events = await repository.get_unpublished_events(limit=20)
        assert len(events) == 10
        # event_data is already a dict when using JSONB
        indices = [e.event_data["index"] for e in events]
        assert sorted(indices) == list(range(10))
