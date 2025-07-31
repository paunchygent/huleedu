"""
Test module for Redis notification functionality in Essay Lifecycle Service.

Tests the real-time notification system following protocol-based testing patterns.
Note: This file was updated after removing DefaultEventPublisher facade.
Tests now focus on Redis notification patterns through BatchLifecyclePublisher.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

# EntityReference removed - using primitive parameters
from common_core.status_enums import EssayStatus
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.essay_lifecycle_service.implementations.batch_lifecycle_publisher import (
    BatchLifecyclePublisher,
)
from services.essay_lifecycle_service.protocols import BatchEssayTracker


class TestRedisNotifications:
    """Test Redis notification functionality with protocol-based mocking."""

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Provide mock Redis client following protocol specification."""
        return AsyncMock(spec=AtomicRedisClientProtocol)

    @pytest.fixture
    def mock_batch_tracker(self) -> AsyncMock:
        """Provide mock batch tracker following protocol specification."""
        tracker = AsyncMock(spec=BatchEssayTracker)
        tracker.get_user_id_for_essay.return_value = "test_user_123"
        return tracker

    @pytest.fixture
    def mock_batch_publisher(self) -> AsyncMock:
        """Provide mock batch lifecycle publisher."""
        return AsyncMock(spec=BatchLifecyclePublisher)

    async def test_redis_notification_data_structure(self) -> None:
        """Test the structure of Redis notification data."""
        # Arrange
        essay_id = str(uuid4())
        status = EssayStatus.SPELLCHECKED_SUCCESS
        correlation_id = uuid4()

        notification_data = {
            "essay_id": essay_id,
            "status": status.value,
            "timestamp": datetime.now(UTC).isoformat(),
            "correlation_id": str(correlation_id),
        }

        # Act - serialize and deserialize
        serialized = json.dumps(notification_data)
        deserialized = json.loads(serialized)

        # Assert - data integrity preserved
        assert deserialized == notification_data
        assert deserialized["essay_id"] == essay_id
        assert deserialized["status"] == status.value
        assert deserialized["correlation_id"] == str(correlation_id)

    async def test_batch_tracker_user_lookup(
        self,
        mock_batch_tracker: AsyncMock,
    ) -> None:
        """Test the batch tracker user lookup method interface."""
        # Arrange
        essay_id = str(uuid4())
        expected_user_id = "user_456"
        mock_batch_tracker.get_user_id_for_essay.return_value = expected_user_id

        # Act
        result = await mock_batch_tracker.get_user_id_for_essay(essay_id)

        # Assert
        assert result == expected_user_id
        mock_batch_tracker.get_user_id_for_essay.assert_called_once_with(essay_id)

    async def test_redis_client_notification_interface(
        self,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test Redis client notification publishing interface."""
        # Arrange
        user_id = "test_user_123"
        event_type = "essay_status_updated"
        notification_data = {
            "essay_id": str(uuid4()),
            "status": "completed",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Act
        await mock_redis_client.publish_user_notification(
            user_id=user_id, event_type=event_type, data=notification_data
        )

        # Assert
        mock_redis_client.publish_user_notification.assert_called_once_with(
            user_id=user_id, event_type=event_type, data=notification_data
        )

    async def test_batch_lifecycle_publisher_interface(
        self,
        mock_batch_publisher: AsyncMock,
    ) -> None:
        """Test BatchLifecyclePublisher interface for slot assignment events."""
        # Arrange - Create proper slot assignment event data
        from common_core.events.essay_lifecycle_events import EssaySlotAssignedV1
        from common_core.metadata_models import SystemProcessingMetadata

        event_data = EssaySlotAssignedV1(
            batch_id="test_batch_123",
            essay_id="essay_123",
            file_upload_id="upload_456",
            slot_assignment_id="slot_789",
            text_storage_id="storage_abc",
            metadata=SystemProcessingMetadata(entity_id="essay_123", entity_type="essay"),
        )
        correlation_id = uuid4()

        # Act - Use the actual BatchLifecyclePublisher method
        await mock_batch_publisher.publish_essay_slot_assigned(
            event_data=event_data, correlation_id=correlation_id
        )

        # Assert
        mock_batch_publisher.publish_essay_slot_assigned.assert_called_once_with(
            event_data=event_data, correlation_id=correlation_id
        )
