"""
Test module for Redis notification functionality in Essay Lifecycle Service.

Tests the real-time notification system following protocol-based testing patterns.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.error_enums import ErrorCode
from common_core.metadata_models import EntityReference
from common_core.status_enums import EssayStatus
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.essay_lifecycle_service.implementations.event_publisher import DefaultEventPublisher
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
        return AsyncMock(spec=BatchEssayTracker)

    @pytest.fixture
    def mock_kafka_bus(self) -> AsyncMock:
        """Provide mock Kafka bus."""
        return AsyncMock()

    @pytest.fixture
    def mock_settings(self) -> AsyncMock:
        """Provide mock settings."""
        settings = AsyncMock()
        settings.SERVICE_NAME = "essay_lifecycle_service"
        return settings

    @pytest.fixture
    def event_publisher(
        self,
        mock_kafka_bus: AsyncMock,
        mock_settings: AsyncMock,
        mock_redis_client: AsyncMock,
        mock_batch_tracker: AsyncMock,
    ) -> DefaultEventPublisher:
        """Provide event publisher with all mocked dependencies."""
        return DefaultEventPublisher(
            kafka_bus=mock_kafka_bus,
            settings=mock_settings,
            redis_client=mock_redis_client,
            batch_tracker=mock_batch_tracker,
        )

    async def test_publish_status_update_with_valid_user_id(
        self,
        event_publisher: DefaultEventPublisher,
        mock_redis_client: AsyncMock,
        mock_batch_tracker: AsyncMock,
    ) -> None:
        """Test Redis notification publishing when user_id is found."""
        # Arrange
        essay_id = str(uuid4())
        user_id = "test_user_123"
        status = EssayStatus.ALL_PROCESSING_COMPLETED
        correlation_id = uuid4()

        essay_ref = EntityReference(entity_id=essay_id, entity_type="essay")
        mock_batch_tracker.get_user_id_for_essay.return_value = user_id

        # Act
        await event_publisher.publish_status_update(essay_ref, status, correlation_id)

        # Assert
        mock_batch_tracker.get_user_id_for_essay.assert_called_once_with(essay_id)
        mock_redis_client.publish_user_notification.assert_called_once()

        # Verify notification call arguments
        call_args = mock_redis_client.publish_user_notification.call_args
        assert call_args[1]["user_id"] == user_id
        assert call_args[1]["event_type"] == "essay_status_updated"

        notification_data = call_args[1]["data"]
        assert notification_data["essay_id"] == essay_id
        assert notification_data["status"] == status.value
        assert notification_data["correlation_id"] == str(correlation_id)
        assert "timestamp" in notification_data

    async def test_publish_status_update_without_user_id(
        self,
        event_publisher: DefaultEventPublisher,
        mock_redis_client: AsyncMock,
        mock_batch_tracker: AsyncMock,
    ) -> None:
        """Test Redis notification behavior when user_id is not found."""
        # Arrange
        essay_id = str(uuid4())
        status = EssayStatus.SPELLCHECK_FAILED

        essay_ref = EntityReference(entity_id=essay_id, entity_type="essay")
        mock_batch_tracker.get_user_id_for_essay.return_value = None

        # Act
        correlation_id = uuid4()
        await event_publisher.publish_status_update(essay_ref, status, correlation_id)

        # Assert
        mock_batch_tracker.get_user_id_for_essay.assert_called_once_with(essay_id)
        mock_redis_client.publish_user_notification.assert_not_called()

    async def test_notification_data_serialization_round_trip(self) -> None:
        """Test serialization round-trip for notification data (contract testing)."""
        # Arrange
        notification_data = {
            "essay_id": str(uuid4()),
            "status": "completed",
            "timestamp": datetime.now(UTC).isoformat(),
            "correlation_id": str(uuid4()),
        }

        # Act - serialize and deserialize
        serialized = json.dumps(notification_data)
        deserialized = json.loads(serialized)

        # Assert - data integrity preserved
        assert deserialized == notification_data
        assert deserialized["essay_id"] == notification_data["essay_id"]
        assert deserialized["status"] == notification_data["status"]
        assert deserialized["timestamp"] == notification_data["timestamp"]
        assert deserialized["correlation_id"] == notification_data["correlation_id"]

    async def test_redis_client_error_handling(
        self,
        event_publisher: DefaultEventPublisher,
        mock_redis_client: AsyncMock,
        mock_batch_tracker: AsyncMock,
    ) -> None:
        """Test error handling when Redis client fails."""
        # Arrange
        essay_id = str(uuid4())
        user_id = "test_user_123"
        status = EssayStatus.SPELLCHECKING_IN_PROGRESS

        essay_ref = EntityReference(entity_id=essay_id, entity_type="essay")
        mock_batch_tracker.get_user_id_for_essay.return_value = user_id
        mock_redis_client.publish_user_notification.side_effect = Exception(
            "Redis connection failed"
        )

        # Act - should raise HuleEduError with EXTERNAL_SERVICE_ERROR
        correlation_id = uuid4()
        with pytest.raises(HuleEduError) as exc_info:
            await event_publisher.publish_status_update(essay_ref, status, correlation_id)

        # Assert - Redis call was attempted
        mock_redis_client.publish_user_notification.assert_called_once()

        # Validate error structure
        error = exc_info.value
        assert error.error_detail.error_code == ErrorCode.EXTERNAL_SERVICE_ERROR
        assert "Redis" in error.error_detail.message
        assert error.error_detail.service == "essay_lifecycle_service"
        assert error.error_detail.operation == "_publish_essay_status_to_redis"

    async def test_batch_tracker_lookup_method(
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
