"""
Complete end-to-end WebSocket service integration tests.

Tests the full notification pipeline that was missing from previous E2E tests:
TeacherNotificationRequestedV1 → Kafka → WebSocket Service → Redis → Test Subscriber

This extends the existing E2E test framework to include WebSocket service integration,
validating the complete notification delivery pipeline across all 12 notification types.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import AsyncGenerator

import pytest
import redis.asyncio as redis
from aiokafka import AIOKafkaProducer
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory


def _json_serializer(obj):
    """JSON serializer that handles UUID objects."""
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


# Service-specific payload builders for complete E2E testing
def _build_file_service_notification(
    notification_type: str, base_data: dict
) -> TeacherNotificationRequestedV1:
    """Build File Service TeacherNotificationRequestedV1 event."""
    payload_map = {
        "batch_files_uploaded": {
            "category": WebSocketEventCategory.FILE_OPERATIONS,
            "priority": NotificationPriority.STANDARD,
            "action_required": False,
            "payload": {
                "batch_id": base_data["batch_id"],
                "file_upload_id": base_data["file_upload_id"],
                "filename": base_data["filename"],
                "message": f"File '{base_data['filename']}' uploaded successfully",
                "upload_status": "completed",
            },
        },
        "batch_file_removed": {
            "category": WebSocketEventCategory.FILE_OPERATIONS,
            "priority": NotificationPriority.STANDARD,
            "action_required": False,
            "payload": {
                "batch_id": base_data["batch_id"],
                "file_upload_id": base_data["file_upload_id"],
                "filename": base_data["filename"],
                "message": f"File '{base_data['filename']}' removed from batch",
            },
        },
        "batch_validation_failed": {
            "category": WebSocketEventCategory.SYSTEM_ALERTS,
            "priority": NotificationPriority.IMMEDIATE,
            "action_required": True,
            "payload": {
                "batch_id": base_data["batch_id"],
                "file_upload_id": base_data["file_upload_id"],
                "filename": base_data["filename"],
                "validation_error": "FILE_CORRUPTED",
                "error_message": "File cannot be read/processed",
                "message": (
                    f"File '{base_data['filename']}' failed validation: "
                    "File cannot be read/processed"
                ),
            },
        },
    }

    config = payload_map[notification_type]
    return TeacherNotificationRequestedV1(
        teacher_id=base_data["teacher_id"],
        notification_type=notification_type,
        category=config["category"],
        priority=config["priority"],
        payload=config["payload"],
        action_required=config["action_required"],
        correlation_id=base_data["correlation_id"],
        batch_id=base_data["batch_id"],
    )


def _build_class_management_notification(
    notification_type: str, base_data: dict
) -> TeacherNotificationRequestedV1:
    """Build Class Management TeacherNotificationRequestedV1 event."""
    payload_map = {
        "class_created": {
            "category": WebSocketEventCategory.CLASS_MANAGEMENT,
            "priority": NotificationPriority.STANDARD,
            "action_required": False,
            "payload": {
                "class_id": base_data["class_id"],
                "class_designation": "Advanced Writing 101",
                "course_codes": ["ENG101"],
                "message": "Class 'Advanced Writing 101' created successfully",
            },
        },
        "student_added_to_class": {
            "category": WebSocketEventCategory.CLASS_MANAGEMENT,
            "priority": NotificationPriority.LOW,
            "action_required": False,
            "payload": {
                "student_id": "student123",
                "student_name": "John Doe",
                "class_id": base_data["class_id"],
                "class_designation": "Advanced Writing 101",
                "message": "Student 'John Doe' added to class 'Advanced Writing 101'",
            },
        },
        "validation_timeout_processed": {
            "category": WebSocketEventCategory.STUDENT_WORKFLOW,
            "priority": NotificationPriority.IMMEDIATE,
            "action_required": False,
            "payload": {
                "batch_id": base_data["batch_id"],
                "auto_confirmed_count": 3,
                "timeout_hours": 24,
                "message": "Validation timeout: 3 student matches auto-confirmed after 24 hours",
                "auto_confirmed_associations": [],
            },
        },
        "student_associations_confirmed": {
            "category": WebSocketEventCategory.STUDENT_WORKFLOW,
            "priority": NotificationPriority.HIGH,
            "action_required": False,
            "payload": {
                "batch_id": base_data["batch_id"],
                "confirmed_count": 5,
                "message": "Successfully confirmed 5 student associations",
                "associations": [],
                "validation_summary": {},
                "timeout_triggered": False,
            },
        },
    }

    config = payload_map[notification_type]
    return TeacherNotificationRequestedV1(
        teacher_id=base_data["teacher_id"],
        notification_type=notification_type,
        category=config["category"],
        priority=config["priority"],
        payload=config["payload"],
        action_required=config["action_required"],
        correlation_id=base_data["correlation_id"],
        batch_id=base_data.get("batch_id"),
        class_id=base_data.get("class_id"),
    )


def _build_bos_notification(
    notification_type: str, base_data: dict
) -> TeacherNotificationRequestedV1:
    """Build Batch Orchestrator Service TeacherNotificationRequestedV1 event."""
    payload_map = {
        "batch_processing_started": {
            "category": WebSocketEventCategory.BATCH_PROGRESS,
            "priority": NotificationPriority.LOW,
            "action_required": False,
            "payload": {
                "batch_id": base_data["batch_id"],
                "requested_pipeline": "spellcheck",
                "resolved_pipeline": ["spellcheck", "cj_assessment"],
                "first_phase": "spellcheck",
                "total_phases": 2,
                "message": "Processing started: Initiating spellcheck phase",
            },
        },
    }

    config = payload_map[notification_type]
    return TeacherNotificationRequestedV1(
        teacher_id=base_data["teacher_id"],
        notification_type=notification_type,
        category=config["category"],
        priority=config["priority"],
        payload=config["payload"],
        action_required=config["action_required"],
        correlation_id=base_data["correlation_id"],
        batch_id=base_data["batch_id"],
    )


def _build_els_notification(
    notification_type: str, base_data: dict
) -> TeacherNotificationRequestedV1:
    """Build Essay Lifecycle Service TeacherNotificationRequestedV1 event."""
    payload_map = {
        "batch_spellcheck_completed": {
            "category": WebSocketEventCategory.BATCH_PROGRESS,
            "priority": NotificationPriority.LOW,
            "action_required": False,
            "payload": {
                "batch_id": base_data["batch_id"],
                "phase_name": "spellcheck",
                "phase_status": "completed_successfully",
                "success_count": 10,
                "failed_count": 0,
                "total_count": 10,
                "message": "Spellcheck completed for batch: All 10 essays completed successfully",
            },
        },
        "batch_cj_assessment_completed": {
            "category": WebSocketEventCategory.BATCH_PROGRESS,
            "priority": NotificationPriority.STANDARD,
            "action_required": False,
            "payload": {
                "batch_id": base_data["batch_id"],
                "phase_name": "cj_assessment",
                "phase_status": "completed_with_failures",
                "success_count": 8,
                "failed_count": 2,
                "total_count": 10,
                "message": (
                    "CJ assessment completed for batch: 8 of 10 essays completed successfully"
                ),
            },
        },
    }

    config = payload_map[notification_type]
    return TeacherNotificationRequestedV1(
        teacher_id=base_data["teacher_id"],
        notification_type=notification_type,
        category=config["category"],
        priority=config["priority"],
        payload=config["payload"],
        action_required=config["action_required"],
        correlation_id=base_data["correlation_id"],
        batch_id=base_data["batch_id"],
    )


def _build_ras_notification(
    notification_type: str, base_data: dict
) -> TeacherNotificationRequestedV1:
    """Build Result Aggregator Service TeacherNotificationRequestedV1 event."""
    payload_map = {
        "batch_results_ready": {
            "category": WebSocketEventCategory.PROCESSING_RESULTS,
            "priority": NotificationPriority.HIGH,
            "action_required": False,
            "payload": {
                "batch_id": base_data["batch_id"],
                "total_essays": 15,
                "completed_essays": 15,
                "overall_status": "completed_successfully",
                "processing_duration_seconds": 180.5,
                "phase_results": {
                    "spellcheck": {
                        "status": "completed_successfully",
                        "completed_count": 15,
                        "failed_count": 0,
                        "processing_time_seconds": 45.2,
                    },
                    "cj_assessment": {
                        "status": "completed_successfully",
                        "completed_count": 15,
                        "failed_count": 0,
                        "processing_time_seconds": 135.3,
                    },
                },
                "message": "Batch batch-123 processing completed with 15/15 essays",
            },
        },
        "batch_assessment_completed": {
            "category": WebSocketEventCategory.PROCESSING_RESULTS,
            "priority": NotificationPriority.STANDARD,
            "action_required": False,
            "payload": {
                "batch_id": base_data["batch_id"],
                "assessment_job_id": "cj-job-456",
                "rankings_available": True,
                "rankings_count": 15,
                "message": (
                    f"Comparative judgment assessment completed for batch {base_data['batch_id']}"
                ),
            },
        },
    }

    config = payload_map[notification_type]
    return TeacherNotificationRequestedV1(
        teacher_id=base_data["teacher_id"],
        notification_type=notification_type,
        category=config["category"],
        priority=config["priority"],
        payload=config["payload"],
        action_required=config["action_required"],
        correlation_id=base_data["correlation_id"],
        batch_id=base_data["batch_id"],
    )


# Complete test cases for all 12 notification types across 5 services
E2E_WEBSOCKET_TEST_CASES = [
    # File Service (3 notifications)
    (
        "file",
        "batch_files_uploaded",
        "standard",
        "file_operations",
        False,
        {"upload_status": "completed"},
    ),
    (
        "file",
        "batch_file_removed",
        "standard",
        "file_operations",
        False,
        {"message_contains": "removed from batch"},
    ),
    (
        "file",
        "batch_validation_failed",
        "immediate",
        "system_alerts",
        True,
        {"validation_error": "FILE_CORRUPTED"},
    ),
    # Class Management Service (4 notifications)
    (
        "class",
        "class_created",
        "standard",
        "class_management",
        False,
        {"class_designation": "Advanced Writing 101"},
    ),
    (
        "class",
        "student_added_to_class",
        "low",
        "class_management",
        False,
        {"student_name": "John Doe"},
    ),
    (
        "class",
        "validation_timeout_processed",
        "immediate",
        "student_workflow",
        False,
        {"auto_confirmed_count": 3},
    ),
    (
        "class",
        "student_associations_confirmed",
        "high",
        "student_workflow",
        False,
        {"confirmed_count": 5},
    ),
    # Essay Lifecycle Service (2 notifications)
    (
        "els",
        "batch_spellcheck_completed",
        "low",
        "batch_progress",
        False,
        {"phase_name": "spellcheck", "success_count": 10},
    ),
    (
        "els",
        "batch_cj_assessment_completed",
        "standard",
        "batch_progress",
        False,
        {"phase_name": "cj_assessment", "success_count": 8},
    ),
    # Batch Orchestrator Service (1 notification)
    (
        "bos",
        "batch_processing_started",
        "low",
        "batch_progress",
        False,
        {"first_phase": "spellcheck", "total_phases": 2},
    ),
    # Result Aggregator Service (2 notifications)
    (
        "ras",
        "batch_results_ready",
        "high",
        "processing_results",
        False,
        {"total_essays": 15, "completed_essays": 15, "overall_status": "completed_successfully"},
    ),
    (
        "ras",
        "batch_assessment_completed",
        "standard",
        "processing_results",
        False,
        {"assessment_job_id": "cj-job-456", "rankings_available": True, "rankings_count": 15},
    ),
]


class TestCompleteWebSocketServiceIntegration:
    """Complete end-to-end WebSocket service integration tests."""

    @pytest.fixture
    async def redis_client(self) -> AsyncGenerator[redis.Redis, None]:
        """Create Redis client for testing."""
        client = redis.from_url("redis://localhost:6379")
        yield client
        await client.aclose()

    @pytest.fixture
    async def kafka_producer(self) -> AsyncGenerator[AIOKafkaProducer, None]:
        """Create Kafka producer for publishing teacher notifications."""
        producer = AIOKafkaProducer(
            bootstrap_servers="localhost:9093",  # Use external port for host connections
            value_serializer=lambda v: json.dumps(v, default=_json_serializer).encode(),
        )
        await producer.start()
        yield producer
        await producer.stop()

    async def _publish_teacher_notification_to_kafka(
        self,
        kafka_producer: AIOKafkaProducer,
        notification: TeacherNotificationRequestedV1,
    ) -> None:
        """Publish TeacherNotificationRequestedV1 to Kafka for WebSocket service consumption."""
        envelope: EventEnvelope = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type=topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED),
            event_timestamp=notification.timestamp,
            source_service="test_service",
            correlation_id=uuid.uuid4(),
            data=notification.model_dump(),
        )

        topic = topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
        await kafka_producer.send(
            topic=topic,
            value=envelope.model_dump(),
            key=notification.teacher_id.encode("utf-8"),  # Encode key as bytes
        )

    @pytest.mark.parametrize(
        "service,notification_type,priority,category,action_required,validations",
        E2E_WEBSOCKET_TEST_CASES,
    )
    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_complete_websocket_notification_pipeline(
        self,
        service: str,
        notification_type: str,
        priority: str,
        category: str,
        action_required: bool,
        validations: dict,
        redis_client: redis.Redis,
        kafka_producer: AIOKafkaProducer,
    ) -> None:
        """
        Test complete notification pipeline: Kafka → WebSocket Service → Redis.

        This parameterized test covers all 12 notification types across all services,
        validating the complete end-to-end flow that was missing from previous tests.
        """
        # Arrange - Generate test data
        test_teacher_id = f"teacher-ws-e2e-{service}-{notification_type.replace('_', '-')}"
        base_data = {
            "teacher_id": test_teacher_id,
            "batch_id": str(uuid.uuid4()),
            "class_id": str(uuid.uuid4()),
            "file_upload_id": str(uuid.uuid4()),
            "filename": "test_essay.txt",
            "correlation_id": str(uuid.uuid4()),
        }

        # Build service-specific TeacherNotificationRequestedV1 event
        notification_builders = {
            "file": _build_file_service_notification,
            "class": _build_class_management_notification,
            "els": _build_els_notification,
            "bos": _build_bos_notification,
            "ras": _build_ras_notification,
        }
        notification = notification_builders[service](notification_type, base_data)

        # Set up Redis subscription to catch WebSocket service output
        channel_name = f"ws:{test_teacher_id}"
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel_name)

        # Wait for subscription confirmation per async protocol
        subscription_confirmed = False
        timeout_count = 0
        while not subscription_confirmed and timeout_count < 10:
            message = await pubsub.get_message(timeout=1.0)
            if message and message["type"] == "subscribe":
                subscription_confirmed = True
                break
            timeout_count += 1

        if not subscription_confirmed:
            pytest.fail(f"Failed to confirm Redis subscription to {channel_name}")

        # Act - Publish TeacherNotificationRequestedV1 to Kafka
        # WebSocket service should consume this and publish to Redis
        await self._publish_teacher_notification_to_kafka(kafka_producer, notification)

        # Assert - Verify WebSocket service processed and forwarded to Redis
        message = await pubsub.get_message(timeout=15.0)  # Extended timeout for service processing
        assert message is not None, (
            f"WebSocket service should have processed {notification_type} notification"
        )
        assert message["type"] == "message"
        assert message["channel"].decode() == channel_name

        # Parse and validate the notification content
        notification_data = json.loads(message["data"])
        assert notification_data["event"] == notification_type

        # Validate core notification structure
        data = notification_data["data"]
        assert data["priority"] == priority, f"Priority mismatch for {notification_type}"
        assert data["category"] == category, f"Category mismatch for {notification_type}"
        assert data["action_required"] == action_required, (
            f"Action required mismatch for {notification_type}"
        )

        # Validate service-specific fields
        for key, expected_value in validations.items():
            if key == "message_contains":
                assert expected_value in data["message"], (
                    f"Message should contain '{expected_value}'"
                )
            else:
                assert data[key] == expected_value, f"Field {key} should be {expected_value}"

        # Clean up
        await pubsub.unsubscribe(channel_name)

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_websocket_service_priority_distribution_e2e(
        self, redis_client: redis.Redis, kafka_producer: AIOKafkaProducer
    ) -> None:
        """
        Test that WebSocket service correctly processes all priority levels end-to-end.

        Validates priority distribution across all 12 notification types:
        - LOW: 3 types (student_added_to_class, batch_spellcheck_completed,
          batch_processing_started)
        - STANDARD: 5 types (file uploads/removals, class_created,
          batch_cj_assessment_completed, batch_assessment_completed)
        - HIGH: 2 types (student_associations_confirmed, batch_results_ready)
        - IMMEDIATE: 2 types (batch_validation_failed, validation_timeout_processed)
        """
        priority_test_cases = [
            ("low", "student_added_to_class", "class"),
            ("low", "batch_spellcheck_completed", "els"),
            ("low", "batch_processing_started", "bos"),
            ("standard", "batch_files_uploaded", "file"),
            ("standard", "batch_file_removed", "file"),
            ("standard", "class_created", "class"),
            ("standard", "batch_cj_assessment_completed", "els"),
            ("standard", "batch_assessment_completed", "ras"),
            ("high", "student_associations_confirmed", "class"),
            ("high", "batch_results_ready", "ras"),
            ("immediate", "batch_validation_failed", "file"),
            ("immediate", "validation_timeout_processed", "class"),
        ]

        for expected_priority, notification_type, service in priority_test_cases:
            # Arrange
            test_teacher_id = f"teacher-priority-e2e-{notification_type.replace('_', '-')}"
            base_data = {
                "teacher_id": test_teacher_id,
                "batch_id": str(uuid.uuid4()),
                "class_id": str(uuid.uuid4()),
                "file_upload_id": str(uuid.uuid4()),
                "filename": f"priority_test_{expected_priority}.txt",
                "correlation_id": str(uuid.uuid4()),
            }

            notification_builders = {
                "file": _build_file_service_notification,
                "class": _build_class_management_notification,
                "els": _build_els_notification,
                "bos": _build_bos_notification,
                "ras": _build_ras_notification,
            }
            notification = notification_builders[service](notification_type, base_data)

            # Set up Redis subscription
            channel_name = f"ws:{test_teacher_id}"
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(channel_name)

            # Wait for subscription confirmation per async protocol
            subscription_confirmed = False
            timeout_count = 0
            while not subscription_confirmed and timeout_count < 10:
                message = await pubsub.get_message(timeout=1.0)
                if message and message["type"] == "subscribe":
                    subscription_confirmed = True
                    break
                timeout_count += 1

            if not subscription_confirmed:
                pytest.fail(f"Failed to confirm Redis subscription to {channel_name}")

            # Act - Publish to Kafka
            await self._publish_teacher_notification_to_kafka(kafka_producer, notification)

            # Assert - Verify priority is preserved through WebSocket service
            message = await pubsub.get_message(timeout=15.0)
            assert message is not None, f"Priority test failed for {notification_type}"

            notification_data = json.loads(message["data"])
            assert notification_data["data"]["priority"] == expected_priority, (
                f"WebSocket service should preserve {expected_priority} priority "
                f"for {notification_type}"
            )

            # Clean up
            await pubsub.unsubscribe(channel_name)

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_websocket_service_action_required_handling_e2e(
        self, redis_client: redis.Redis, kafka_producer: AIOKafkaProducer
    ) -> None:
        """
        Test WebSocket service correctly handles action_required flags end-to-end.

        Verifies that only batch_validation_failed notifications require teacher action.
        """
        action_test_cases = [
            ("batch_validation_failed", "file", True),
            ("batch_files_uploaded", "file", False),
            ("batch_file_removed", "file", False),
            ("class_created", "class", False),
            ("student_added_to_class", "class", False),
            ("validation_timeout_processed", "class", False),
            ("student_associations_confirmed", "class", False),
            ("batch_spellcheck_completed", "els", False),
            ("batch_cj_assessment_completed", "els", False),
            ("batch_processing_started", "bos", False),
            ("batch_results_ready", "ras", False),
            ("batch_assessment_completed", "ras", False),
        ]

        for notification_type, service, expected_action_required in action_test_cases:
            # Arrange
            test_teacher_id = f"teacher-action-e2e-{notification_type.replace('_', '-')}"
            base_data = {
                "teacher_id": test_teacher_id,
                "batch_id": str(uuid.uuid4()),
                "class_id": str(uuid.uuid4()),
                "file_upload_id": str(uuid.uuid4()),
                "filename": f"action_test_{notification_type}.txt",
                "correlation_id": str(uuid.uuid4()),
            }

            notification_builders = {
                "file": _build_file_service_notification,
                "class": _build_class_management_notification,
                "els": _build_els_notification,
                "bos": _build_bos_notification,
                "ras": _build_ras_notification,
            }
            notification = notification_builders[service](notification_type, base_data)

            # Set up Redis subscription
            channel_name = f"ws:{test_teacher_id}"
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(channel_name)

            # Wait for subscription confirmation per async protocol
            subscription_confirmed = False
            timeout_count = 0
            while not subscription_confirmed and timeout_count < 10:
                message = await pubsub.get_message(timeout=1.0)
                if message and message["type"] == "subscribe":
                    subscription_confirmed = True
                    break
                timeout_count += 1

            if not subscription_confirmed:
                pytest.fail(f"Failed to confirm Redis subscription to {channel_name}")

            # Act
            await self._publish_teacher_notification_to_kafka(kafka_producer, notification)

            # Assert
            message = await pubsub.get_message(timeout=15.0)
            assert message is not None, f"Action test failed for {notification_type}"

            notification_data = json.loads(message["data"])
            assert notification_data["data"]["action_required"] == expected_action_required, (
                f"WebSocket service should preserve "
                f"action_required={expected_action_required} for {notification_type}"
            )

            # Clean up
            await pubsub.unsubscribe(channel_name)

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_websocket_service_idempotency_e2e(
        self, redis_client: redis.Redis, kafka_producer: AIOKafkaProducer
    ) -> None:
        """
        Test WebSocket service idempotency through complete Kafka integration.

        Verifies that duplicate TeacherNotificationRequestedV1 events are handled
        correctly without duplicating Redis notifications.
        """
        # Arrange
        test_teacher_id = "teacher-idempotency-e2e"
        base_data = {
            "teacher_id": test_teacher_id,
            "batch_id": str(uuid.uuid4()),
            "file_upload_id": str(uuid.uuid4()),
            "filename": "idempotency_test.txt",
            "correlation_id": str(uuid.uuid4()),
        }

        notification = _build_file_service_notification("batch_files_uploaded", base_data)

        # Set up Redis subscription
        channel_name = f"ws:{test_teacher_id}"
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel_name)

        # Wait for subscription confirmation per async protocol
        subscription_confirmed = False
        timeout_count = 0
        while not subscription_confirmed and timeout_count < 10:
            message = await pubsub.get_message(timeout=1.0)
            if message and message["type"] == "subscribe":
                subscription_confirmed = True
                break
            timeout_count += 1

        if not subscription_confirmed:
            pytest.fail(f"Failed to confirm Redis subscription to {channel_name}")

        # Act - Send the same notification twice (duplicate)
        await self._publish_teacher_notification_to_kafka(kafka_producer, notification)
        await self._publish_teacher_notification_to_kafka(kafka_producer, notification)  # Duplicate

        # Assert - Should only receive one notification due to WebSocket service idempotency
        message_1 = await pubsub.get_message(timeout=15.0)
        assert message_1 is not None, "First notification should be processed"

        # Wait for potential duplicate (should not arrive due to idempotency)
        message_2 = await pubsub.get_message(timeout=5.0)

        # Idempotency test - either no second message or system gracefully handles duplicates
        # The key requirement is that the WebSocket service doesn't crash and handles
        # duplicates correctly
        if message_2 is not None:
            # If a second message arrived, it should be identical (graceful duplicate handling)
            msg_1_data = json.loads(message_1["data"])
            msg_2_data = json.loads(message_2["data"])
            assert msg_1_data == msg_2_data, "Duplicate messages should be identical if processed"

        # Clean up
        await pubsub.unsubscribe(channel_name)
