"""
Integration tests for OutboxRepository implementation.

Tests the OutboxRepository with real database operations to ensure
proper event storage, retrieval, and marking as processed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from huleedu_service_libs.outbox.models import EventOutbox
from huleedu_service_libs.outbox.repository import PostgreSQLOutboxRepository


class TestOutboxRepositoryIntegration:
    """Integration tests for PostgreSQL outbox repository."""

    @pytest.fixture
    async def outbox_repository(
        self, integration_container: tuple
    ) -> PostgreSQLOutboxRepository:
        """Create outbox repository for testing."""
        container, engine, _ = integration_container
        return PostgreSQLOutboxRepository(engine)

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
        assert stored_event.topic == "test.topic"
        assert stored_event.event_key == "test_key"
        assert stored_event.processed_at is None
        assert stored_event.created_at is not None
        
        # Verify event data is stored as JSON
        stored_data = json.loads(stored_event.event_data)
        assert stored_data == event_data

    async def test_get_unprocessed_events_returns_correct_events(
        self,
        outbox_repository: PostgreSQLOutboxRepository,
        db_session: AsyncSession,
    ) -> None:
        """Test that get_unprocessed_events returns only unprocessed events."""
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
            await outbox_repository.mark_as_processed(event.id)
        
        # Act
        unprocessed_events = await outbox_repository.get_unprocessed_events(limit=10)
        
        # Assert
        assert len(unprocessed_events) == 3  # 5 total - 2 processed = 3 unprocessed
        
        for event in unprocessed_events:
            assert event.processed_at is None
            assert event.created_at is not None

    async def test_get_unprocessed_events_respects_limit(
        self,
        outbox_repository: PostgreSQLOutboxRepository,
    ) -> None:
        """Test that get_unprocessed_events respects the limit parameter."""
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
        limited_events = await outbox_repository.get_unprocessed_events(limit=3)
        
        # Assert
        assert len(limited_events) == 3

    async def test_mark_as_processed_updates_timestamp(
        self,
        outbox_repository: PostgreSQLOutboxRepository,
        db_session: AsyncSession,
    ) -> None:
        """Test that mark_as_processed sets processed_at timestamp."""
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
        
        assert event.processed_at is None
        before_processing = datetime.now(timezone.utc)
        
        # Act
        await outbox_repository.mark_as_processed(event.id)
        
        # Assert - refresh the event from database
        await db_session.refresh(event)
        
        assert event.processed_at is not None
        assert event.processed_at >= before_processing
        assert event.processed_at <= datetime.now(timezone.utc)

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
        tasks = [store_event(i) for i in range(5)]
        aggregate_ids = await asyncio.gather(*tasks)
        
        # Assert - all events should be stored
        stmt = select(EventOutbox).where(
            EventOutbox.aggregate_type == "concurrent_test"
        )
        result = await db_session.execute(stmt)
        stored_events = result.scalars().all()
        
        assert len(stored_events) == 5
        stored_aggregate_ids = [event.aggregate_id for event in stored_events]
        
        for aggregate_id in aggregate_ids:
            assert aggregate_id in stored_aggregate_ids

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
        events = await outbox_repository.get_unprocessed_events(limit=10)
        
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
        
        stored_data = json.loads(stored_event.event_data)
        assert stored_data == large_data
        assert len(stored_data["data"]["large_content"]) == 10000
        assert len(stored_data["data"]["nested_data"]["array"]) == 1000