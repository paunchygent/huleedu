"""
Simple End-to-End Test for Content Validation.

Tests that content validation failures publish EssayValidationFailedV1 events
with appropriate error codes (EMPTY_CONTENT, CONTENT_TOO_SHORT).

Modernized to use ServiceTestManager and KafkaTestManager utilities.
"""

from typing import Any

import pytest

from tests.utils.auth_manager import AuthTestManager, create_test_teacher
from tests.utils.kafka_test_manager import kafka_event_monitor, kafka_manager
from tests.utils.service_test_manager import ServiceTestManager


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.asyncio
async def test_content_validation_failures_publish_events():
    """
    Test content validation failures publish proper events using utilities.

    Validates:
    - ServiceTestManager handles file upload correctly
    - KafkaTestManager captures validation failure events
    - Events contain proper validation error information
    """
    # Initialize with authentication support
    auth_manager = AuthTestManager()
    service_manager = ServiceTestManager(auth_manager=auth_manager)
    test_teacher = create_test_teacher()

    # Validate File Service is available
    endpoints = await service_manager.get_validated_endpoints()
    if "file_service" not in endpoints:
        pytest.skip("File Service not available for validation testing")

    # Create batch first (required for file uploads)
    batch_id, correlation_id = await service_manager.create_batch(
        expected_essay_count=1, course_code="ENG5", user=test_teacher
    )
    print(f"✅ Batch created: {batch_id}")

    # Use KafkaTestManager for event monitoring
    topics = ["huleedu.file.essay.validation.failed.v1"]
    async with kafka_event_monitor("validation_failure_test", topics) as consumer:
        # Upload invalid file (empty content should trigger validation failure)
        files = [{"name": "invalid_essay.txt", "content": b""}]

        try:
            upload_result = await service_manager.upload_files(
                batch_id=batch_id, files=files, user=test_teacher, correlation_id=correlation_id
            )
            upload_correlation_id = upload_result["correlation_id"]

            print(f"✅ Invalid file uploaded for batch {batch_id}")
            print(f"   Upload correlation ID: {upload_correlation_id}")

        except RuntimeError as e:
            pytest.fail(f"ServiceTestManager upload failed: {e}")

    # Create test files: 1 valid, 2 content validation failures
    files = [
        {
            "name": "valid_essay.txt",
            "content": "This is a valid essay with enough content to pass validation.",
        },
        {
            "name": "invalid_essay_empty.txt",
            "content": "",  # Triggers RAW_STORAGE_FAILED (Content Service rejects empty bodies)
        },
        {
            "name": "invalid_essay_short.txt",
            "content": "Too short",  # This will trigger CONTENT_TOO_SHORT validation failure
        },
    ]

    # Set up Kafka monitoring for validation events using utility
    validation_topics = [
        "huleedu.file.essay.validation.failed.v1",
        "huleedu.file.essay.content.provisioned.v1",
    ]

    async with kafka_event_monitor("validation_failures_test", validation_topics) as consumer:
        # Upload files using utility (with same user who created the batch)
        try:
            upload_result = await service_manager.upload_files(
                batch_id=batch_id,
                files=files,
                user=test_teacher,  # Use same user who created the batch
                correlation_id=correlation_id,
            )
            print(f"✅ File upload successful: {upload_result}")
        except RuntimeError as e:
            pytest.fail(f"File upload failed: {e}")

        # Collect validation events using utility
        def validation_event_filter(event_data: dict[str, Any]) -> bool:
            """Filter for validation events from our specific test batch."""
            # Handle EventEnvelope format
            if "data" in event_data and isinstance(event_data["data"], dict):
                inner_data = event_data["data"]
                return inner_data.get("batch_id") == batch_id
            # Handle direct event format
            return event_data.get("batch_id") == batch_id

        try:
            # Collect events - expect 1 content provision + 2 validation failures
            events = await kafka_manager.collect_events(
                consumer,
                expected_count=3,
                timeout_seconds=30,
                event_filter=validation_event_filter,
            )

            print(f"📊 Collected {len(events)} validation events")

            # Separate events by topic for validation
            validation_failure_events = []
            content_provision_events = []

            for event in events:
                topic = event.get("topic", "")
                event_data = event.get("data", {})

                if "validation.failed" in topic:
                    validation_failure_events.append(event)
                    print(f"🔴 VALIDATION FAILURE: {event_data}")
                elif "content.provisioned" in topic:
                    content_provision_events.append(event)
                    print(f"✅ CONTENT PROVISIONED: {event_data}")

            # Validate we got expected events
            assert len(content_provision_events) >= 1, (
                f"Should have at least 1 content provision (valid essay), "
                f"got {len(content_provision_events)}"
            )
            assert len(validation_failure_events) >= 2, (
                f"Should have 2 validation failures (empty + short), "
                f"got {len(validation_failure_events)}"
            )

            # Check that validation failure events have the expected error codes
            # Note: Empty files fail with RAW_STORAGE_FAILED because Content Service
            # rejects empty request bodies
            empty_content_failures = []
            content_too_short_failures = []
            raw_storage_failures = []

            for event in validation_failure_events:
                event_envelope = event.get("data", {})
                event_payload = event_envelope.get("data", {})
                error_code = event_payload.get("validation_error_code")
                if error_code == "EMPTY_CONTENT":
                    empty_content_failures.append(event)
                elif error_code == "CONTENT_TOO_SHORT":
                    content_too_short_failures.append(event)
                elif error_code == "RAW_STORAGE_FAILED":
                    raw_storage_failures.append(event)

            print(f"Empty content failures: {len(empty_content_failures)}")
            print(f"Content too short failures: {len(content_too_short_failures)}")
            print(f"Raw storage failures: {len(raw_storage_failures)}")

            # Critical validation failure assertions
            # Empty files fail with RAW_STORAGE_FAILED because Content Service
            # rejects empty request bodies
            assert len(raw_storage_failures) >= 1, (
                f"Should have at least 1 RAW_STORAGE_FAILED validation failure event (empty file), "
                f"got {len(raw_storage_failures)}"
            )
            assert len(content_too_short_failures) >= 1, (
                f"Should have at least 1 CONTENT_TOO_SHORT validation failure event, "
                f"got {len(content_too_short_failures)}"
            )

            print(
                "✅ Test passed: Content validation failures correctly publish "
                "appropriate validation failure events!",
            )

        except Exception as e:
            pytest.fail(f"Event collection or validation failed: {e}")
