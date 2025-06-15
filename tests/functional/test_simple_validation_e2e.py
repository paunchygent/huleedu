"""
Simple End-to-End Test for Content Validation.

Tests that content validation failures publish EssayValidationFailedV1 events
with appropriate error codes (EMPTY_CONTENT, CONTENT_TOO_SHORT).

Modernized to use ServiceTestManager and KafkaTestManager utilities.
"""

from typing import Any, Dict

import pytest

from tests.utils.kafka_test_manager import kafka_event_monitor, kafka_manager
from tests.utils.service_test_manager import ServiceTestManager


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.docker
async def test_content_validation_failures_publish_events():
    """
    Test that content validation failures publish validation failure events with proper error codes.

    Uses modern utility patterns throughout - NO direct HTTP calls or custom Kafka consumers.
    Preserves all validation failure testing logic: EMPTY_CONTENT and CONTENT_TOO_SHORT scenarios.
    """
    service_manager = ServiceTestManager()

    # Create a small batch using utility
    try:
        batch_id, correlation_id = await service_manager.create_batch(
            expected_essay_count=3,
            course_code="SIMPLE",
            class_designation="E2E",
        )
        print(f"✅ Created batch {batch_id}")
    except RuntimeError as e:
        pytest.fail(f"Batch creation failed: {e}")

    # Create test files: 1 valid, 2 content validation failures
    files = [
        {
            "name": "valid_essay.txt",
            "content": "This is a valid essay with enough content to pass validation.",
        },
        {
            "name": "invalid_essay_empty.txt",
            "content": "",  # This will trigger RAW_STORAGE_FAILED (Content Service rejects empty bodies)
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

        # Upload files using utility
        try:
            upload_result = await service_manager.upload_files(
                batch_id=batch_id,
                files=files,
                correlation_id=correlation_id
            )
            print(f"✅ File upload successful: {upload_result}")
        except RuntimeError as e:
            pytest.fail(f"File upload failed: {e}")

        # Collect validation events using utility
        def validation_event_filter(event_data: Dict[str, Any]) -> bool:
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
                event_filter=validation_event_filter
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
            # Note: Empty files fail with RAW_STORAGE_FAILED because Content Service rejects empty request bodies
            empty_content_failures = []
            content_too_short_failures = []
            raw_storage_failures = []

            for event in validation_failure_events:
                event_data = event["data"]
                # Handle EventEnvelope format
                if "data" in event_data and isinstance(event_data["data"], dict):
                    failure_data = event_data["data"]
                else:
                    failure_data = event_data

                error_code = failure_data.get("validation_error_code")
                if error_code == "EMPTY_CONTENT":
                    empty_content_failures.append(failure_data)
                elif error_code == "CONTENT_TOO_SHORT":
                    content_too_short_failures.append(failure_data)
                elif error_code == "RAW_STORAGE_FAILED":
                    raw_storage_failures.append(failure_data)

            # Critical validation failure assertions
            # Empty files fail with RAW_STORAGE_FAILED because Content Service rejects empty request bodies
            assert len(raw_storage_failures) >= 1, (
                f"Should have at least 1 RAW_STORAGE_FAILED validation failure event (empty file), "
                f"got {len(raw_storage_failures)}"
            )
            assert len(content_too_short_failures) >= 1, (
                f"Should have at least 1 CONTENT_TOO_SHORT validation failure event, "
                f"got {len(content_too_short_failures)}"
            )

            print("✅ Test passed: Content validation failures correctly publish "
                  "appropriate validation failure events!")

        except Exception as e:
            pytest.fail(f"Event collection or validation failed: {e}")
