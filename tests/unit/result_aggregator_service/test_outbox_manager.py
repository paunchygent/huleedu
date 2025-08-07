"""Unit tests for Result Aggregator Service OutboxManager."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.events import EventEnvelope
from huleedu_service_libs.error_handling import HuleEduError

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.outbox_manager import OutboxManager


@pytest.fixture
def mock_outbox_repository():
    """Mock outbox repository."""
    mock = AsyncMock()
    mock.add_event = AsyncMock(return_value=uuid4())
    return mock


@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    mock = AsyncMock()
    mock.lpush = AsyncMock()
    return mock


@pytest.fixture
def settings():
    """Test settings."""
    return Settings()


@pytest.fixture
def outbox_manager(mock_outbox_repository, mock_redis_client, settings):
    """Create OutboxManager instance with mocked dependencies."""
    return OutboxManager(
        outbox_repository=mock_outbox_repository,
        redis_client=mock_redis_client,
        settings=settings,
    )


class TestOutboxManager:
    """Test suite for OutboxManager."""

    @pytest.mark.asyncio
    async def test_publish_to_outbox_success(self, outbox_manager, mock_outbox_repository, mock_redis_client):
        """Test successful event publication to outbox."""
        # Arrange
        correlation_id = uuid4()
        event_data: EventEnvelope = EventEnvelope(
            event_type="test.event.v1",
            source_service="result_aggregator_service",
            correlation_id=correlation_id,
            data={"test": "data"},
        )

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="batch",
            aggregate_id="batch-123",
            event_type="test.event.v1",
            event_data=event_data,
            topic="test-topic",
        )

        # Assert
        mock_outbox_repository.add_event.assert_called_once()
        call_args = mock_outbox_repository.add_event.call_args

        assert call_args.kwargs["aggregate_id"] == "batch-123"
        assert call_args.kwargs["aggregate_type"] == "batch"
        assert call_args.kwargs["event_type"] == "test.event.v1"
        assert call_args.kwargs["topic"] == "test-topic"
        assert call_args.kwargs["event_key"] == "batch-123"

        # Verify event data includes topic
        event_data_arg = call_args.kwargs["event_data"]
        assert event_data_arg["topic"] == "test-topic"
        assert event_data_arg["event_type"] == "test.event.v1"

        # Verify Redis notification
        mock_redis_client.lpush.assert_called_once_with(
            "outbox:wake:result_aggregator_service", "1"
        )

    @pytest.mark.asyncio
    async def test_publish_to_outbox_with_partition_key(self, outbox_manager, mock_outbox_repository):
        """Test event publication with custom partition key in metadata."""
        # Arrange
        correlation_id = uuid4()
        event_data: EventEnvelope = EventEnvelope(
            event_type="test.event.v1",
            source_service="result_aggregator_service",
            correlation_id=correlation_id,
            data={"test": "data"},
            metadata={"partition_key": "custom-key"},
        )

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="batch",
            aggregate_id="batch-123",
            event_type="test.event.v1",
            event_data=event_data,
            topic="test-topic",
        )

        # Assert
        call_args = mock_outbox_repository.add_event.call_args
        assert call_args.kwargs["event_key"] == "custom-key"

    @pytest.mark.asyncio
    async def test_publish_to_outbox_no_repository(self, mock_redis_client, settings):
        """Test error when outbox repository is not configured."""
        # Arrange
        outbox_manager = OutboxManager(
            outbox_repository=None,  # type: ignore[arg-type]
            redis_client=mock_redis_client,
            settings=settings,
        )

        event_data: EventEnvelope = EventEnvelope(
            event_type="test.event.v1",
            source_service="result_aggregator_service",
            correlation_id=uuid4(),
            data={"test": "data"},
        )

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="batch",
                aggregate_id="batch-123",
                event_type="test.event.v1",
                event_data=event_data,
                topic="test-topic",
            )

        assert "Outbox repository not configured" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_publish_to_outbox_invalid_event_data(self, outbox_manager):
        """Test error when event data is not a Pydantic model."""
        # Arrange
        invalid_event_data = {"not": "a pydantic model"}

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="batch",
                aggregate_id="batch-123",
                event_type="test.event.v1",
                event_data=invalid_event_data,
                topic="test-topic",
            )

        assert "Failed to store event in outbox" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_notify_relay_worker_success(self, outbox_manager, mock_redis_client):
        """Test successful relay worker notification."""
        # Act
        await outbox_manager.notify_relay_worker()

        # Assert
        mock_redis_client.lpush.assert_called_once_with(
            "outbox:wake:result_aggregator_service", "1"
        )

    @pytest.mark.asyncio
    async def test_notify_relay_worker_failure_does_not_raise(self, outbox_manager, mock_redis_client):
        """Test that relay worker notification failure doesn't raise exception."""
        # Arrange
        mock_redis_client.lpush.side_effect = Exception("Redis error")

        # Act - should not raise
        await outbox_manager.notify_relay_worker()

        # Assert
        mock_redis_client.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_to_outbox_repository_error(self, outbox_manager, mock_outbox_repository):
        """Test error handling when repository fails."""
        # Arrange
        mock_outbox_repository.add_event.side_effect = Exception("Database error")

        event_data: EventEnvelope = EventEnvelope(
            event_type="test.event.v1",
            source_service="result_aggregator_service",
            correlation_id=uuid4(),
            data={"test": "data"},
        )

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="batch",
                aggregate_id="batch-123",
                event_type="test.event.v1",
                event_data=event_data,
                topic="test-topic",
            )

        assert "Failed to store event in outbox" in str(exc_info.value)
        assert exc_info.value.error_detail.service == "result_aggregator_service"
        assert exc_info.value.error_detail.operation == "publish_to_outbox"
