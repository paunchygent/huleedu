"""
Integration tests for OutboxRepository implementation.

Tests the OutboxRepository with real database operations to ensure
proper event storage, retrieval, and marking as processed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from huleedu_service_libs.outbox.models import EventOutbox
from huleedu_service_libs.outbox.repository import PostgreSQLOutboxRepository
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from services.file_service.tests.integration.conftest import TestFileServiceOutboxPatternIntegration


class TestOutboxRepositoryIntegration(TestFileServiceOutboxPatternIntegration):
    """Integration tests for PostgreSQL outbox repository."""

    @pytest.fixture(autouse=True)
    async def clean_outbox_table(self, db_session: AsyncSession) -> None:
        """Clean the outbox table before each test to ensure isolation."""
        # Delete all existing events from the outbox table
        await db_session.execute(delete(EventOutbox))
        await db_session.commit()

    @pytest.fixture
    async def outbox_repository(self, test_engine: AsyncEngine) -> PostgreSQLOutboxRepository:
        """Create outbox repository for testing."""
        return PostgreSQLOutboxRepository(test_engine)

    async def test_add_event_stores_in_database(
        self,
        outbox_repository: PostgreSQLOutboxRepository,
        db_session: AsyncSession,
    ) -> None:
        """Test that add_event stores event in database with correct fields."""
        # Arrange
        aggregate_id = str(uuid4())
        event_data = {
            "event_type": "test.event",
            "source_service": "file_service",
            "correlation_id": str(uuid4()),
            "data": {"test": "data", "value": 42},
            "metadata": {"trace_id": "trace_123"},
        }

        # Act
        await outbox_repository.add_event(
            aggregate_id=aggregate_id,
            aggregate_type="test_aggregate",
            event_type="test.event.v1",
            event_data=event_data,
            topic="test.topic",
            event_key="test_key",
        )

        # Assert - verify event is stored
        stmt = select(EventOutbox).where(EventOutbox.aggregate_id == aggregate_id)
        result = await db_session.execute(stmt)
        stored_event = result.scalar_one()

        assert stored_event.aggregate_id == aggregate_id
        assert stored_event.aggregate_type == "test_aggregate"
        assert stored_event.event_type == "test.event.v1"
        assert stored_event.event_key == "test_key"
        assert stored_event.published_at is None
        assert stored_event.created_at is not None

        # Verify event data is stored correctly (SQLAlchemy auto-deserializes JSON)
        # Topic is now a separate column, not embedded in event_data
        assert stored_event.event_data == event_data
        assert stored_event.topic == "test.topic"

    async def test_get_unpublished_events_returns_correct_events(
        self,
        outbox_repository: PostgreSQLOutboxRepository,
        db_session: AsyncSession,
    ) -> None:
        """Test that get_unpublished_events returns only unpublished events."""
        # Arrange - create mix of processed and unprocessed events
        events_data = []
        for i in range(5):
            aggregate_id = str(uuid4())
            event_data = {"test": "data", "index": i}

            await outbox_repository.add_event(
                aggregate_id=aggregate_id,
                aggregate_type="test_aggregate",
                event_type=f"test.event.{i}",
                event_data=event_data,
                topic="test.topic",
                event_key=f"key_{i}",
            )
            events_data.append((aggregate_id, event_data))

        # Mark some events as processed
        stmt = select(EventOutbox).limit(2)
        result = await db_session.execute(stmt)
        events_to_process = result.scalars().all()

        for event in events_to_process:
            await outbox_repository.mark_event_published(event.id)

        # Act
        unpublished_events = await outbox_repository.get_unpublished_events(limit=10)

        # Assert
        assert len(unpublished_events) == 3  # 5 total - 2 published = 3 unpublished

        for unpublished_event in unpublished_events:
            assert unpublished_event.published_at is None
            assert unpublished_event.created_at is not None

    async def test_get_unpublished_events_respects_limit(
        self,
        outbox_repository: PostgreSQLOutboxRepository,
    ) -> None:
        """Test that get_unpublished_events respects the limit parameter."""
        # Arrange - create more events than limit
        for i in range(10):
            await outbox_repository.add_event(
                aggregate_id=str(uuid4()),
                aggregate_type="test_aggregate",
                event_type=f"test.event.{i}",
                event_data={"test": "data", "index": i},
                topic="test.topic",
                event_key=f"key_{i}",
            )

        # Act
        limited_events = await outbox_repository.get_unpublished_events(limit=3)

        # Assert
        assert len(limited_events) == 3

    async def test_mark_as_published_updates_timestamp(
        self,
        outbox_repository: PostgreSQLOutboxRepository,
        db_session: AsyncSession,
    ) -> None:
        """Test that mark_event_published sets published_at timestamp."""
        # Arrange
        aggregate_id = str(uuid4())
        event_data = {"test": "data"}

        await outbox_repository.add_event(
            aggregate_id=aggregate_id,
            aggregate_type="test_aggregate",
            event_type="test.event",
            event_data=event_data,
            topic="test.topic",
            event_key="test_key",
        )

        # Get the event ID
        stmt = select(EventOutbox).where(EventOutbox.aggregate_id == aggregate_id)
        result = await db_session.execute(stmt)
        event = result.scalar_one()

        assert event.published_at is None
        before_publishing = datetime.now(timezone.utc)

        # Act
        await outbox_repository.mark_event_published(event.id)

        # Assert - refresh the event from database
        await db_session.refresh(event)

        assert event.published_at is not None
        assert event.published_at >= before_publishing
        assert event.published_at <= datetime.now(timezone.utc)

    async def test_concurrent_event_storage(
        self,
        outbox_repository: PostgreSQLOutboxRepository,
        db_session: AsyncSession,
    ) -> None:
        """Test that concurrent event storage works correctly."""
        import asyncio

        # Arrange
        async def store_event(index: int) -> str:
            aggregate_id = str(uuid4())
            await outbox_repository.add_event(
                aggregate_id=aggregate_id,
                aggregate_type="concurrent_test",
                event_type=f"concurrent.test.{index}",
                event_data={"test": "data", "index": index},
                topic="concurrent.topic",
                event_key=f"concurrent_key_{index}",
            )
            return aggregate_id

        # Act - store events concurrently
        tasks = [store_event(i) for i in range(20)]
        aggregate_ids = await asyncio.gather(*tasks)

        # Assert - all events should be stored
        # Filter only the events we just created
        stored_aggregate_ids = []
        for aggregate_id in aggregate_ids:
            stmt = select(EventOutbox).where(EventOutbox.aggregate_id == aggregate_id)
            result = await db_session.execute(stmt)
            event = result.scalar_one_or_none()
            assert event is not None
            stored_aggregate_ids.append(event.aggregate_id)

        assert len(stored_aggregate_ids) == 20
        assert set(stored_aggregate_ids) == set(aggregate_ids)

    async def test_event_ordering_by_created_at(
        self,
        outbox_repository: PostgreSQLOutboxRepository,
    ) -> None:
        """Test that events are returned in creation order."""
        # Arrange - create events with slight delays to ensure different timestamps
        import asyncio

        aggregate_ids = []
        for i in range(3):
            aggregate_id = str(uuid4())
            await outbox_repository.add_event(
                aggregate_id=aggregate_id,
                aggregate_type="ordering_test",
                event_type=f"ordering.test.{i}",
                event_data={"test": "data", "index": i},
                topic="ordering.topic",
                event_key=f"ordering_key_{i}",
            )
            aggregate_ids.append(aggregate_id)
            await asyncio.sleep(0.01)  # Small delay to ensure different timestamps

        # Act
        events = await outbox_repository.get_unpublished_events(limit=10)

        # Assert - events should be in creation order (oldest first)
        ordered_events = [e for e in events if e.aggregate_type == "ordering_test"]
        assert len(ordered_events) == 3

        # Verify chronological order
        for i in range(len(ordered_events) - 1):
            assert ordered_events[i].created_at <= ordered_events[i + 1].created_at

    async def test_large_event_data_storage(
        self,
        outbox_repository: PostgreSQLOutboxRepository,
        db_session: AsyncSession,
    ) -> None:
        """Test storage of large event data payloads."""
        # Arrange - create large event data
        large_data = {
            "event_type": "large.data.test",
            "source_service": "file_service",
            "correlation_id": str(uuid4()),
            "data": {
                "large_content": "x" * 10000,  # 10KB of data
                "nested_data": {
                    "array": list(range(1000)),
                    "text": "Large text content " * 100,
                },
            },
            "metadata": {"size": "large"},
        }

        aggregate_id = str(uuid4())

        # Act
        await outbox_repository.add_event(
            aggregate_id=aggregate_id,
            aggregate_type="large_data_test",
            event_type="large.data.test",
            event_data=large_data,
            topic="large.data.topic",
            event_key="large_key",
        )

        # Assert - verify large data is stored and retrievable
        stmt = select(EventOutbox).where(EventOutbox.aggregate_id == aggregate_id)
        result = await db_session.execute(stmt)
        stored_event = result.scalar_one()

        # SQLAlchemy auto-deserializes JSON
        # Topic is now a separate column, not embedded in event_data
        assert stored_event.event_data == large_data
        assert stored_event.topic == "large.data.topic"
        assert len(stored_event.event_data["data"]["large_content"]) == 10000
        assert len(stored_event.event_data["data"]["nested_data"]["array"]) == 1000
