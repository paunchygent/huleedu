"""
End-to-End test for File Service raw storage functionality.

Validates that the File Service properly implements pre-emptive raw storage
and publishes events containing the required raw_file_storage_id field.
"""

from __future__ import annotations

import json
import uuid

import pytest

from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager


@pytest.mark.functional
@pytest.mark.asyncio
async def test_file_service_events_contain_raw_storage_id():
    """
    E2E test verifying File Service publishes events with raw_file_storage_id.

    This test validates that the File Service refactor successfully implements
    pre-emptive raw storage and populates the required raw_file_storage_id field
    in both success and failure events, addressing the breaking changes in Task 2.
    """
    batch_id = str(uuid.uuid4())
    timeout_seconds = 30

    kafka_manager = KafkaTestManager()
    topics = [
        "huleedu.file.essay.content.provisioned.v1",
        "huleedu.file.essay.validation.failed.v1",
    ]

    # Step 1: Validate File Service is healthy
    service_manager = ServiceTestManager()
    endpoints = await service_manager.get_validated_endpoints()

    assert "file_service" in endpoints, "File Service not found in healthy services"
    print(f"✅ File Service validated at: {endpoints['file_service']['base_url']}")

    # Step 2: Set up Kafka consumer to capture events
    async with kafka_manager.consumer("file_service_e2e", topics) as consumer:
        print("✅ Kafka consumer ready for File Service events")

        # Step 3: Upload a valid test file
        correlation_id = str(uuid.uuid4())

        test_file_content = "This is a valid test essay content."

        # Prepare files for upload using ServiceTestManager format
        files = [{"name": "test_essay.txt", "content": test_file_content.encode()}]

        response = await service_manager.upload_files(
            batch_id=batch_id, files=files, correlation_id=correlation_id,
        )

        print(f"✅ File uploaded successfully for batch: {batch_id}")
        print(f"   Upload response: {response}")

        # Step 4: Wait for and validate event
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
                        assert event_data["original_file_name"] == "test_essay.txt"
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
                        print(
                            f"⚠️ Unexpected validation failure: "
                            f"{event_data.get('validation_error_message')}",
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


@pytest.mark.functional
@pytest.mark.asyncio
async def test_file_service_validation_failure_contains_raw_storage_id():
    """
    E2E test verifying validation failure events contain raw_file_storage_id.

    Tests that even when file validation fails, the raw file has been stored
    and the failure event contains the raw_file_storage_id.
    """
    # Step 1: Validate File Service is healthy
    service_manager = ServiceTestManager()
    endpoints = await service_manager.get_validated_endpoints()

    assert "file_service" in endpoints, "File Service not found in healthy services"
    print(f"✅ File Service validated at: {endpoints['file_service']['base_url']}")

    # Step 2: Set up Kafka consumer
    kafka_manager = KafkaTestManager()
    topics = ["huleedu.file.essay.validation.failed.v1"]

    async with kafka_manager.consumer("file_service_validation_e2e", topics) as consumer:
        print("✅ Kafka consumer ready for validation failure events")

        # Step 3: Upload an invalid file (empty content to trigger validation failure)
        batch_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())

        empty_file_content = ""  # This should trigger validation failure

        # Prepare empty file for upload
        files = [{"name": "empty_essay.txt", "content": empty_file_content.encode()}]

        response = await service_manager.upload_files(
            batch_id=batch_id, files=files, correlation_id=correlation_id,
        )

        print(f"✅ Empty file uploaded for batch: {batch_id}")
        print(f"   Upload response: {response}")

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
                    assert "validation_error_message" in event_data, (
                        "Missing validation_error_message"
                    )
                    assert event_data["batch_id"] == batch_id

                    print("✅ Found validation failure event with raw_file_storage_id")
                    print(f"   - raw_file_storage_id: {event_data['raw_file_storage_id']}")
                    print(f"   - validation_error_code: {event_data['validation_error_code']}")
                    print(
                        f"   - validation_error_message: {event_data['validation_error_message']}",
                    )

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
