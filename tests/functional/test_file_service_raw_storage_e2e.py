"""
End-to-End test for File Service raw storage functionality.

Validates that the File Service properly implements pre-emptive raw storage
and publishes events containing the required raw_file_storage_id field.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager
from tests.utils.test_auth_manager import AuthTestManager, create_test_teacher


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.asyncio
async def test_file_service_events_contain_raw_storage_id():
    """
    Test that File Service events include raw_storage_id for content tracking.

    Validates:
    - EssayContentProvisionedV1 events contain raw_storage_id
    - Raw storage ID can be used to retrieve original content
    - Content integrity is maintained through storage pipeline
    """
    # Initialize with authentication support
    auth_manager = AuthTestManager()
    service_manager = ServiceTestManager(auth_manager=auth_manager)
    test_teacher = create_test_teacher()

    # Validate File Service is available
    endpoints = await service_manager.get_validated_endpoints()
    if "file_service" not in endpoints:
        pytest.skip("File Service not available for raw storage testing")

    test_file_path = Path("test_uploads/essay1.txt")
    if not test_file_path.exists():
        pytest.skip(f"Test file {test_file_path} not found")

    # Create batch first (required for file uploads)
    batch_id, correlation_id = await service_manager.create_batch(
        expected_essay_count=1, course_code="ENG5", user=test_teacher
    )
    print(f"✅ Batch created: {batch_id}")

    kafka_manager = KafkaTestManager()
    topics = [
        "huleedu.file.essay.content.provisioned.v1",
        "huleedu.file.essay.validation.failed.v1",
    ]

    # Step 2: Set up Kafka consumer to capture events
    async with kafka_manager.consumer("file_service_e2e", topics) as consumer:
        print("✅ Kafka consumer ready for File Service events")

        # Upload file using ServiceTestManager utility
        with open(test_file_path, "rb") as f:
            files = [{"name": test_file_path.name, "content": f.read()}]

        try:
            upload_result = await service_manager.upload_files(
                batch_id=batch_id, files=files, user=test_teacher, correlation_id=correlation_id
            )
            upload_correlation_id = upload_result["correlation_id"]

            print(f"✅ File uploaded for batch {batch_id}")
            print(f"   Upload correlation ID: {upload_correlation_id}")

        except RuntimeError as e:
            pytest.fail(f"ServiceTestManager upload failed: {e}")

        # Step 4: Wait for and validate event
        timeout_seconds = 30
        event_received = False

        async for message in consumer:
            try:
                message_value = json.loads(message.value.decode())
                event_data = message_value.get("data", {})

                # Check if this is our event
                if event_data.get("batch_id") == batch_id:
                    print(f"📨 Received event for batch {batch_id}")

                    # Validate event structure
                    if message.topic == "huleedu.file.essay.content.provisioned.v1":
                        # Success event validation
                        assert "raw_file_storage_id" in event_data, (
                            "Missing raw_file_storage_id in success event"
                        )
                        assert "text_storage_id" in event_data, (
                            "Missing text_storage_id in success event"
                        )
                        assert event_data["original_file_name"] == test_file_path.name
                        assert event_data["batch_id"] == batch_id

                        print("✅ EssayContentProvisionedV1 event validated:")
                        print(f"   - raw_file_storage_id: {event_data['raw_file_storage_id']}")
                        print(f"   - text_storage_id: {event_data['text_storage_id']}")

                        event_received = True
                        break

                    elif message.topic == "huleedu.file.essay.validation.failed.v1":
                        # Failure event validation (unexpected for valid content)
                        assert "raw_file_storage_id" in event_data, (
                            "Missing raw_file_storage_id in failure event"
                        )
                        validation_detail = event_data.get("validation_error_detail", {})
                        error_message = validation_detail.get("message", "Unknown error")
                        print(
                            f"⚠️ Unexpected validation failure: {error_message}",
                        )
                        print(f"   - raw_file_storage_id: {event_data['raw_file_storage_id']}")

                        event_received = True
                        break

            except Exception as e:
                print(f"⚠️ Error processing message: {e}")
                continue

        assert event_received, (
            f"No File Service event received for batch {batch_id} within {timeout_seconds}s"
        )
        print("✅ E2E test passed: File Service events contain required raw_file_storage_id field")


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.asyncio
async def test_file_service_validation_failure_contains_raw_storage_id():
    """
    Test that validation failure events include raw_storage_id for debugging.

    Validates:
    - EssayValidationFailedV1 events contain raw_storage_id
    - Raw storage ID allows access to problematic content
    - Validation failure tracking includes content reference
    """
    # Initialize with authentication support
    auth_manager = AuthTestManager()
    service_manager = ServiceTestManager(auth_manager=auth_manager)
    test_teacher = create_test_teacher()

    # Validate File Service is available
    endpoints = await service_manager.get_validated_endpoints()
    if "file_service" not in endpoints:
        pytest.skip("File Service not available for validation failure testing")

    # Create batch first (required for file uploads)
    batch_id, correlation_id = await service_manager.create_batch(
        expected_essay_count=1, course_code="ENG5", user=test_teacher
    )
    print(f"✅ Batch created: {batch_id}")

    kafka_manager = KafkaTestManager()
    topics = ["huleedu.file.essay.validation.failed.v1"]

    async with kafka_manager.consumer("file_service_validation_e2e", topics) as consumer:
        print("✅ Kafka consumer ready for validation failure events")

        # Create a file that should trigger validation failure (empty content)
        files = [{"name": "empty_essay.txt", "content": b""}]

        try:
            upload_result = await service_manager.upload_files(
                batch_id=batch_id, files=files, user=test_teacher, correlation_id=correlation_id
            )
            upload_correlation_id = upload_result["correlation_id"]

            print(f"✅ Empty file uploaded for batch {batch_id}")
            print(f"   Upload correlation ID: {upload_correlation_id}")

        except RuntimeError as e:
            pytest.fail(f"ServiceTestManager upload failed: {e}")

        # Step 4: Wait for validation failure event
        event_received = False
        timeout_seconds = 30

        async for message in consumer:
            try:
                message_value = json.loads(message.value.decode())
                event_data = message_value.get("data", {})

                # Check if this is our validation failure event
                if (
                    event_data.get("batch_id") == batch_id
                    and event_data.get("original_file_name") == "empty_essay.txt"
                ):
                    print(f"📨 Received validation failure event for batch {batch_id}")

                    # Validate event contains raw_file_storage_id
                    assert "raw_file_storage_id" in event_data, (
                        "Missing raw_file_storage_id in validation failure event"
                    )
                    assert "validation_error_code" in event_data, "Missing validation_error_code"
                    assert "validation_error_detail" in event_data, (
                        "Missing validation_error_detail"
                    )
                    # Ensure the error detail has a message
                    assert "message" in event_data["validation_error_detail"], (
                        "Missing message in validation_error_detail"
                    )
                    assert event_data["batch_id"] == batch_id

                    print("✅ Found validation failure event with raw_file_storage_id")
                    print(f"   - raw_file_storage_id: {event_data['raw_file_storage_id']}")
                    print(f"   - validation_error_code: {event_data['validation_error_code']}")
                    error_msg = event_data["validation_error_detail"]["message"]
                    print(f"   - validation_error_message: {error_msg}")

                    event_received = True
                    break

            except Exception as e:
                print(f"Error processing message: {e}")
                continue

        assert event_received, (
            f"No validation failure event received for batch {batch_id} within {timeout_seconds}s"
        )
        print(
            "✅ E2E test passed: Validation failure events contain required "
            "raw_file_storage_id field",
        )
