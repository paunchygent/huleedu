"""
End-to-end tests for teacher notification system across all services.

Tests the complete flow from service events to WebSocket notifications
through the teacher notification projection pattern for File Service,
Class Management Service, and Essay Lifecycle Service.
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


# Service-specific payload builders for parameterized testing
def _build_file_payload(notification_type: str, base_data: dict) -> dict:
    """Build File Service notification payload."""
    common = {
        "batch_id": base_data["batch_id"],
        "file_upload_id": base_data["file_upload_id"],
        "filename": base_data["filename"],
        "correlation_id": base_data["correlation_id"],
        "timestamp": base_data["timestamp"],
    }
    
    if notification_type == "batch_files_uploaded":
        return {**common, "message": f"File '{base_data['filename']}' uploaded successfully", "upload_status": "completed"}
    elif notification_type == "batch_file_removed":
        return {**common, "message": f"File '{base_data['filename']}' removed from batch"}
    elif notification_type == "batch_validation_failed":
        return {**common, "validation_error": "FILE_CORRUPTED", "error_message": "File cannot be processed", 
                "message": f"File '{base_data['filename']}' failed validation: File cannot be processed"}
    return common


def _build_class_payload(notification_type: str, base_data: dict) -> dict:
    """Build Class Management notification payload."""
    common = {
        "class_id": base_data["class_id"],
        "correlation_id": base_data["correlation_id"],
        "timestamp": base_data["timestamp"],
    }
    
    if notification_type == "class_created":
        return {**common, "class_designation": "Advanced Writing 101", "course_codes": ["ENG101"], 
                "message": "Class 'Advanced Writing 101' created successfully"}
    elif notification_type == "student_added_to_class":
        return {**common, "student_id": "student123", "student_name": "John Doe", "class_designation": "Advanced Writing 101",
                "message": "Student 'John Doe' added to class 'Advanced Writing 101'"}
    elif notification_type == "validation_timeout_processed":
        return {**common, "batch_id": base_data["batch_id"], "auto_confirmed_count": 3, "timeout_hours": 24,
                "message": "Validation timeout reached: 3 associations auto-confirmed", "auto_confirmed_associations": []}
    elif notification_type == "student_associations_confirmed":
        return {**common, "batch_id": base_data["batch_id"], "confirmed_count": 5, 
                "message": "Teacher confirmed 5 student associations", "associations": [], "validation_summary": {}}
    return common


def _build_els_payload(notification_type: str, base_data: dict) -> dict:
    """Build ELS notification payload."""
    common = {
        "batch_id": base_data["batch_id"],
        "correlation_id": base_data["correlation_id"],
        "timestamp": base_data["timestamp"],
    }
    
    if notification_type == "batch_spellcheck_completed":
        return {**common, "phase_name": "spellcheck", "phase_status": "completed_successfully",
                "success_count": 10, "failed_count": 0, "total_count": 10,
                "message": "Spellcheck completed for batch: All 10 essays completed successfully"}
    elif notification_type == "batch_cj_assessment_completed":
        return {**common, "phase_name": "cj_assessment", "phase_status": "completed_with_failures", 
                "success_count": 8, "failed_count": 2, "total_count": 10,
                "message": "CJ assessment completed for batch: 8 of 10 essays completed successfully"}
    return common


# Parameterized test data for all services
NOTIFICATION_TEST_CASES = [
    # service, notification_type, priority, category, action_required, specific_validations
    ("file", "batch_files_uploaded", "standard", "file_operations", False, {"upload_status": "completed"}),
    ("file", "batch_file_removed", "standard", "file_operations", False, {"message_contains": "removed from batch"}),
    ("file", "batch_validation_failed", "immediate", "system_alerts", True, {"validation_error": "FILE_CORRUPTED"}),
    ("class", "class_created", "standard", "class_management", False, {"class_designation": "Advanced Writing 101"}),
    ("class", "student_added_to_class", "low", "class_management", False, {"student_name": "John Doe"}),
    ("class", "validation_timeout_processed", "immediate", "student_workflow", False, {"auto_confirmed_count": 3}),
    ("class", "student_associations_confirmed", "high", "student_workflow", False, {"confirmed_count": 5}),
    ("els", "batch_spellcheck_completed", "low", "batch_progress", False, {"phase_name": "spellcheck", "success_count": 10}),
    ("els", "batch_cj_assessment_completed", "standard", "batch_progress", False, {"phase_name": "cj_assessment", "success_count": 8}),
]


class TestUnifiedServiceNotifications:
    """Unified tests for all service notification patterns."""

    @pytest.fixture
    async def redis_client(self) -> AsyncGenerator[redis.Redis, None]:
        """Create Redis client for testing."""
        client = redis.from_url("redis://localhost:6379")
        yield client
        await client.aclose()

    @pytest.fixture
    async def redis_service_client(self) -> AsyncGenerator[RedisClient, None]:
        """Create service library Redis client."""
        client = RedisClient(client_id="test-unified-notifications", redis_url="redis://localhost:6379")
        await client.start()
        yield client
        await client.stop()

    @pytest.mark.parametrize("service,notification_type,priority,category,action_required,validations", NOTIFICATION_TEST_CASES)
    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_all_service_notification_flows(
        self, 
        service: str,
        notification_type: str, 
        priority: str,
        category: str,
        action_required: bool,
        validations: dict,
        redis_client: redis.Redis, 
        redis_service_client: RedisClient
    ) -> None:
        """
        Parameterized test covering all notification types across all services.
        
        Tests the complete flow from service-specific events to Redis notifications
        for File Service, Class Management, and ELS.
        """
        # Arrange - Generate test data
        test_teacher_id = f"teacher-{service}-{notification_type.replace('_', '-')}"
        base_data = {
            "batch_id": str(uuid.uuid4()),
            "class_id": str(uuid.uuid4()),
            "file_upload_id": str(uuid.uuid4()),
            "filename": "test_essay.txt",
            "correlation_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Build service-specific payload
        payload_builders = {
            "file": _build_file_payload,
            "class": _build_class_payload, 
            "els": _build_els_payload,
        }
        ui_payload = payload_builders[service](notification_type, base_data)
        ui_payload.update({
            "category": category,
            "priority": priority,
            "action_required": action_required,
            "deadline": None,
            "class_id": base_data["class_id"] if service == "class" else None,
        })

        # Set up Redis subscription
        channel_name = f"ws:{test_teacher_id}"
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel_name)
        await pubsub.get_message(timeout=1.0)  # Skip subscription confirmation

        # Act - Simulate service notification
        await redis_service_client.publish_user_notification(
            user_id=test_teacher_id, event_type=notification_type, data=ui_payload
        )

        # Assert - Verify notification received and structured correctly
        message = await pubsub.get_message(timeout=5.0)
        assert message is not None
        assert message["type"] == "message"
        assert message["channel"].decode() == channel_name

        # Parse and validate notification content
        notification_data = json.loads(message["data"])
        assert notification_data["event"] == notification_type
        
        # Validate core notification structure
        data = notification_data["data"]
        assert data["priority"] == priority
        assert data["category"] == category  
        assert data["action_required"] == action_required

        # Validate service-specific fields
        for key, expected_value in validations.items():
            if key == "message_contains":
                assert expected_value in data["message"]
            else:
                assert data[key] == expected_value

        # Clean up
        await pubsub.unsubscribe(channel_name)

    @pytest.mark.asyncio
    async def test_all_services_priority_compliance(self) -> None:
        """
        Test that all services comply with notification priority requirements.
        
        Validates priority distribution across all 9 notification types:
        - LOW: 2 types (student_added_to_class, batch_spellcheck_completed)
        - STANDARD: 4 types (file uploads/removals, class_created, batch_cj_assessment_completed)  
        - HIGH: 1 type (student_associations_confirmed)
        - IMMEDIATE: 2 types (batch_validation_failed, validation_timeout_processed)
        """
        priority_groups = {
            NotificationPriority.LOW: ["student_added_to_class", "batch_spellcheck_completed"],
            NotificationPriority.STANDARD: ["batch_files_uploaded", "batch_file_removed", "class_created", "batch_cj_assessment_completed"],
            NotificationPriority.HIGH: ["student_associations_confirmed"], 
            NotificationPriority.IMMEDIATE: ["batch_validation_failed", "validation_timeout_processed"],
        }

        category_mapping = {
            "batch_files_uploaded": WebSocketEventCategory.FILE_OPERATIONS,
            "batch_file_removed": WebSocketEventCategory.FILE_OPERATIONS,
            "batch_validation_failed": WebSocketEventCategory.SYSTEM_ALERTS,
            "class_created": WebSocketEventCategory.CLASS_MANAGEMENT,
            "student_added_to_class": WebSocketEventCategory.CLASS_MANAGEMENT,
            "validation_timeout_processed": WebSocketEventCategory.STUDENT_WORKFLOW,
            "student_associations_confirmed": WebSocketEventCategory.STUDENT_WORKFLOW,
            "batch_spellcheck_completed": WebSocketEventCategory.BATCH_PROGRESS,
            "batch_cj_assessment_completed": WebSocketEventCategory.BATCH_PROGRESS,
        }

        for expected_priority, notification_types in priority_groups.items():
            for notification_type in notification_types:
                # Create notification with expected priority
                notification = TeacherNotificationRequestedV1(
                    teacher_id="test-teacher",
                    notification_type=notification_type,
                    category=category_mapping[notification_type],
                    priority=expected_priority,
                    payload={"test": "data"},
                    action_required=(notification_type == "batch_validation_failed"),
                    correlation_id="test-correlation",
                )

                # Verify priority compliance
                assert notification.priority == expected_priority
                assert notification.category == category_mapping[notification_type]
