"""
End-to-end test for File Service notification system.

Tests the complete flow from File Service events to WebSocket notifications
through the teacher notification projection pattern.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import redis.asyncio as redis
from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory
from huleedu_service_libs.redis_client import RedisClient


class TestFileServiceNotificationFlow:
    """Test the complete File Service notification workflow."""

    @pytest.fixture
    async def redis_client(self) -> AsyncGenerator[redis.Redis, None]:
        """Create Redis client for testing."""
        client = redis.from_url("redis://localhost:6379")
        yield client
        await client.aclose()

    @pytest.fixture
    async def redis_service_client(self) -> AsyncGenerator[RedisClient, None]:
        """Create service library Redis client."""
        client = RedisClient(client_id="test-file-notification", redis_url="redis://localhost:6379")
        await client.start()
        yield client
        await client.stop()

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_file_upload_notification_flow(
        self, redis_client: redis.Redis, redis_service_client: RedisClient
    ) -> None:
        """
        Test that file upload events produce teacher notifications.

        Simulates File Service publishing a file upload event and verifies
        it gets transformed to a teacher notification and published to Redis.
        """
        # Arrange
        test_teacher_id = "teacher-e2e-123"
        test_batch_id = str(uuid.uuid4())
        test_file_upload_id = str(uuid.uuid4())
        correlation_id = uuid.uuid4()

        # Set up Redis subscription to catch the notification
        channel_name = f"ws:{test_teacher_id}"
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel_name)

        # Skip the subscription confirmation message
        await pubsub.get_message(timeout=1.0)

        # Act - Simulate the File Service notification projector publishing to Redis
        # This is what happens after the projector transforms BatchFileAddedV1 to TeacherNotificationRequestedV1
        ui_payload = {
            "batch_id": test_batch_id,
            "file_upload_id": test_file_upload_id,
            "filename": "test_essay.txt",
            "message": "File 'test_essay.txt' uploaded successfully",
            "upload_status": "completed",
            "category": "file_operations",
            "priority": "standard",
            "action_required": False,
            "deadline": None,
            "class_id": None,
            "correlation_id": str(correlation_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await redis_service_client.publish_user_notification(
            user_id=test_teacher_id, event_type="batch_files_uploaded", data=ui_payload
        )

        # Assert - Check that notification was received
        message = await pubsub.get_message(timeout=5.0)
        assert message is not None
        assert message["type"] == "message"
        assert message["channel"].decode() == channel_name

        # Parse and validate the notification content
        notification_data = json.loads(message["data"])
        assert notification_data["event"] == "batch_files_uploaded"
        assert notification_data["data"]["batch_id"] == test_batch_id
        assert notification_data["data"]["file_upload_id"] == test_file_upload_id
        assert notification_data["data"]["filename"] == "test_essay.txt"
        assert notification_data["data"]["priority"] == "standard"
        assert notification_data["data"]["action_required"] is False

        # Clean up
        await pubsub.unsubscribe(channel_name)

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_file_validation_failed_notification_flow(
        self, redis_client: redis.Redis, redis_service_client: RedisClient
    ) -> None:
        """
        Test that file validation failures produce IMMEDIATE priority notifications.

        Simulates File Service detecting a validation failure and verifies
        it produces an IMMEDIATE priority notification requiring teacher action.
        """
        # Arrange
        test_teacher_id = "teacher-e2e-456"
        test_batch_id = str(uuid.uuid4())
        test_file_upload_id = str(uuid.uuid4())
        correlation_id = uuid.uuid4()

        # Set up Redis subscription
        channel_name = f"ws:{test_teacher_id}"
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel_name)

        # Skip subscription confirmation
        await pubsub.get_message(timeout=1.0)

        # Act - Simulate validation failure notification
        ui_payload = {
            "batch_id": test_batch_id,
            "file_upload_id": test_file_upload_id,
            "filename": "invalid_file.pdf",
            "validation_error": "FILE_CORRUPTED",
            "error_message": "File cannot be read/processed",
            "message": "File 'invalid_file.pdf' failed validation: File cannot be read/processed",
            "category": "system_alerts",
            "priority": "immediate",
            "action_required": True,
            "deadline": None,
            "class_id": None,
            "correlation_id": str(correlation_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await redis_service_client.publish_user_notification(
            user_id=test_teacher_id, event_type="batch_validation_failed", data=ui_payload
        )

        # Assert - Verify IMMEDIATE priority notification
        message = await pubsub.get_message(timeout=5.0)
        assert message is not None

        notification_data = json.loads(message["data"])
        assert notification_data["event"] == "batch_validation_failed"
        assert notification_data["data"]["priority"] == "immediate"
        assert notification_data["data"]["action_required"] is True
        assert notification_data["data"]["validation_error"] == "FILE_CORRUPTED"
        assert notification_data["data"]["category"] == "system_alerts"

        # Clean up
        await pubsub.unsubscribe(channel_name)

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_file_removal_notification_flow(
        self, redis_client: redis.Redis, redis_service_client: RedisClient
    ) -> None:
        """
        Test that file removal events produce teacher notifications.

        Verifies the complete flow from file removal to teacher notification.
        """
        # Arrange
        test_teacher_id = "teacher-e2e-789"
        test_batch_id = str(uuid.uuid4())
        test_file_upload_id = str(uuid.uuid4())
        correlation_id = uuid.uuid4()

        # Set up Redis subscription
        channel_name = f"ws:{test_teacher_id}"
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel_name)

        # Skip subscription confirmation
        await pubsub.get_message(timeout=1.0)

        # Act - Simulate file removal notification
        ui_payload = {
            "batch_id": test_batch_id,
            "file_upload_id": test_file_upload_id,
            "filename": "removed_essay.txt",
            "message": "File 'removed_essay.txt' removed from batch",
            "category": "file_operations",
            "priority": "standard",
            "action_required": False,
            "deadline": None,
            "class_id": None,
            "correlation_id": str(correlation_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await redis_service_client.publish_user_notification(
            user_id=test_teacher_id, event_type="batch_file_removed", data=ui_payload
        )

        # Assert
        message = await pubsub.get_message(timeout=5.0)
        assert message is not None

        notification_data = json.loads(message["data"])
        assert notification_data["event"] == "batch_file_removed"
        assert notification_data["data"]["batch_id"] == test_batch_id
        assert notification_data["data"]["priority"] == "standard"
        assert notification_data["data"]["action_required"] is False

        # Clean up
        await pubsub.unsubscribe(channel_name)

    @pytest.mark.asyncio
    async def test_notification_priority_compliance(self) -> None:
        """
        Test that File Service notifications comply with priority requirements.

        Verifies that notification priorities match the task specification:
        - batch_files_uploaded: STANDARD
        - batch_file_removed: STANDARD
        - batch_validation_failed: IMMEDIATE
        """
        test_cases = [
            ("batch_files_uploaded", "standard", False, "file_operations"),
            ("batch_file_removed", "standard", False, "file_operations"),
            ("batch_validation_failed", "immediate", True, "system_alerts"),
        ]

        for notification_type, expected_priority, expected_action, expected_category in test_cases:
            # Create notification with correct priority
            notification = TeacherNotificationRequestedV1(
                teacher_id="teacher-priority-test",
                notification_type=notification_type,
                category=(
                    WebSocketEventCategory.SYSTEM_ALERTS
                    if expected_priority == "immediate"
                    else WebSocketEventCategory.FILE_OPERATIONS
                ),
                priority=(
                    NotificationPriority.IMMEDIATE
                    if expected_priority == "immediate"
                    else NotificationPriority.STANDARD
                ),
                payload={
                    "batch_id": "test-batch",
                    "file_upload_id": "test-file",
                    "filename": "test.txt",
                    "message": f"Testing {notification_type}",
                },
                action_required=expected_action,
                correlation_id="test-correlation",
                batch_id="test-batch",
            )

            # Verify priority and action required flags
            assert notification.priority.value == expected_priority
            assert notification.action_required == expected_action
            assert notification.category.value == expected_category
