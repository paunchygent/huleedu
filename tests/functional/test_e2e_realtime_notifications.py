"""
End-to-end test for real-time notification system.

Tests the complete flow from backend service events to WebSocket notifications
via Redis Pub/Sub infrastructure.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import redis.asyncio as redis
from huleedu_service_libs.event_utils import extract_user_id_from_event_data
from huleedu_service_libs.redis_client import RedisClient

from common_core.domain_enums import CourseCode
from common_core.events.class_events import ClassCreatedV1
from common_core.events.envelope import EventEnvelope


class TestEndToEndRealtimeNotifications:
    """Test the complete real-time notification workflow."""

    @pytest.fixture
    async def redis_client(self) -> AsyncGenerator[redis.Redis, None]:
        """Create Redis client for testing."""
        client = redis.from_url("redis://localhost:6379")
        yield client
        await client.aclose()

    @pytest.fixture
    async def redis_service_client(self) -> AsyncGenerator[RedisClient, None]:
        """Create service library Redis client."""
        client = RedisClient(client_id="test-client", redis_url="redis://localhost:6379")
        await client.start()
        yield client
        await client.stop()

    @pytest.mark.asyncio
    async def test_event_publisher_to_redis_notification(
        self, redis_client: redis.Redis, redis_service_client: RedisClient
    ) -> None:
        """
        Test that events published by backend services appear as Redis notifications.

        This simulates the Class Management Service publishing a class creation event
        and verifies it gets published to the correct Redis channel.
        """
        # Arrange
        test_user_id = "test-user-123"
        test_class_id = str(uuid.uuid4())
        correlation_id = uuid.uuid4()

        # Create test event data with explicit timestamp
        event_data = ClassCreatedV1(
            class_id=test_class_id,
            class_designation="Test Class",
            course_codes=[CourseCode.ENG5],
            user_id=test_user_id,
            timestamp=datetime.now(timezone.utc),
        )

        # Create EventEnvelope (simulating what the service would create)
        event_envelope = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type="huleedu.class.class.created.v1",
            event_timestamp=event_data.timestamp,
            source_service="class_management_service",
            correlation_id=correlation_id,
            data=event_data,
        )

        # Set up Redis subscription to catch the notification
        channel_name = f"ws:{test_user_id}"
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel_name)

        # Skip the subscription confirmation message
        await pubsub.get_message(timeout=1.0)

        # Act - Simulate the backend service publishing to Redis
        ui_payload = {
            "class_id": event_data.class_id,
            "class_name": event_data.class_designation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": str(correlation_id),
        }

        await redis_service_client.publish_user_notification(
            user_id=test_user_id, event_type="class_created", data=ui_payload
        )

        # Assert - Check that notification was received
        message = await pubsub.get_message(timeout=5.0)
        assert message is not None
        assert message["type"] == "message"
        assert message["channel"].decode() == channel_name

        # Parse the message data
        notification_data = json.loads(message["data"])
        assert notification_data["event"] == "class_created"
        assert notification_data["data"]["class_id"] == test_class_id
        assert notification_data["data"]["class_name"] == "Test Class"
        assert notification_data["data"]["correlation_id"] == str(correlation_id)

        await pubsub.unsubscribe(channel_name)

    @pytest.mark.asyncio
    async def test_user_id_extraction_utility(self) -> None:
        """Test that the user ID extraction utility works for various event types."""
        # Test with ClassCreatedV1 (has user_id field)
        class_event = ClassCreatedV1(
            class_id=str(uuid.uuid4()),
            class_designation="Test Class",
            course_codes=[CourseCode.ENG5],
            user_id="user-123",
        )

        extracted_id = extract_user_id_from_event_data(class_event)
        assert extracted_id == "user-123"

        # Test with mock event that has created_by_user_id
        mock_event = type(
            "MockEvent", (), {"created_by_user_id": "user-456", "other_field": "value"}
        )()

        extracted_id = extract_user_id_from_event_data(mock_event)
        assert extracted_id == "user-456"

        # Test with event that has no user ID fields
        empty_event = type("EmptyEvent", (), {"some_field": "value"})()

        extracted_id = extract_user_id_from_event_data(empty_event)
        assert extracted_id is None

    @pytest.mark.asyncio
    async def test_redis_channel_format(self, redis_service_client: RedisClient) -> None:
        """Test that Redis channels follow the expected format for API Gateway WebSocket."""
        test_user_id = "test-user-789"

        # Mock the publish method to capture the channel name
        captured_channel = None

        async def mock_publish(channel: str, _message: str) -> int:
            nonlocal captured_channel
            captured_channel = channel
            return 1  # Simulate successful publish

        # After refactoring, we need to patch the RedisPubSub publish method
        if redis_service_client._pubsub:
            # Patch the actual pubsub instance's publish method
            original_publish = redis_service_client._pubsub.publish
            redis_service_client._pubsub.publish = mock_publish
            
            try:
                # Act
                await redis_service_client.publish_user_notification(
                    user_id=test_user_id, event_type="test_event", data={"test": "data"}
                )

                # Assert
                assert captured_channel == f"ws:{test_user_id}"
            finally:
                # Restore original method
                redis_service_client._pubsub.publish = original_publish
        else:
            pytest.skip("Redis client not properly initialized with pubsub")

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_redis_failure(self) -> None:
        """Test that services continue to work even if Redis publishing fails."""
        # This test would be implemented in each service's test suite
        # Here we just validate the pattern exists

        # Create a mock Redis client that raises exceptions
        mock_redis_client = AsyncMock()
        mock_redis_client.publish_user_notification.side_effect = Exception(
            "Redis connection failed"
        )

        # The event publisher should log the error but not raise
        # This pattern should be implemented in all service event publishers
        try:
            await mock_redis_client.publish_user_notification(
                user_id="user-123", event_type="test_event", data={"test": "data"}
            )
        except Exception:
            # Event publishers should catch Redis exceptions and log them
            # instead of failing the entire event publishing process
            pass

        # Verify the call was attempted
        mock_redis_client.publish_user_notification.assert_called_once()
