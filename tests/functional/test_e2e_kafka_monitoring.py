"""
E2E Kafka Event Monitoring

Consolidated test suite for Kafka event monitoring workflows, extracted from original Step 2.
Tests event-driven architecture after file uploads and service processing.

Uses modern utility patterns (ServiceTestManager + KafkaTestManager) throughout - NO direct calls.
"""

import uuid
from pathlib import Path
from typing import Any

import pytest

from tests.utils.kafka_test_manager import kafka_event_monitor, kafka_manager
from tests.utils.service_test_manager import ServiceTestManager


class TestE2EKafkaMonitoring:
    """Test Kafka event monitoring for file upload workflows using utilities exclusively."""

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_file_upload_publishes_content_provisioned_event(self):
        """
        Test file upload with Kafka event validation using utilities.

        Validates:
        - ServiceTestManager.upload_files() uploads successfully
        - KafkaTestManager captures EssayContentProvisionedV1 event
        - Event contains correct data structure and correlation ID
        """
        service_manager = ServiceTestManager()

        # Validate File Service is available using utility
        endpoints = await service_manager.get_validated_endpoints()
        if "file_service" not in endpoints:
            pytest.skip("File Service not available for testing")

        test_file_path = Path("test_uploads/essay1.txt")
        if not test_file_path.exists():
            pytest.skip(f"Test file {test_file_path} not found")

        batch_id = f"e2e-event-test-{uuid.uuid4().hex[:8]}"

        # Use KafkaTestManager context manager for event monitoring
        topics = ["huleedu.file.essay.content.provisioned.v1"]
        async with kafka_event_monitor("content_provisioned_test", topics) as consumer:
            # Upload file using ServiceTestManager utility
            with open(test_file_path, "rb") as f:
                files = [{"name": test_file_path.name, "content": f.read()}]

            try:
                upload_result = await service_manager.upload_files(batch_id, files)
                upload_correlation_id = upload_result["correlation_id"]

                print(f"✅ File uploaded for batch {batch_id}")
                print(f"   Upload correlation ID: {upload_correlation_id}")

            except RuntimeError as e:
                pytest.fail(f"ServiceTestManager upload failed: {e}")

            # Collect events using KafkaTestManager utility
            def event_filter(event_data: dict[str, Any]) -> bool:
                """Filter for our specific batch (matching batch_id)."""
                return "data" in event_data and event_data["data"].get("batch_id") == batch_id

            try:
                events = await kafka_manager.collect_events(
                    consumer, expected_count=1, timeout_seconds=30, event_filter=event_filter,
                )

                assert len(events) == 1, f"Expected 1 event, got {len(events)}"

                event_info = events[0]
                envelope_data = event_info["data"]  # EventEnvelope structure

                print(f"📨 Received Kafka event from topic: {event_info['topic']}")

                # Validate EventEnvelope structure
                required_envelope_fields = ["event_id", "event_type", "source_service", "data"]
                for field in required_envelope_fields:
                    assert field in envelope_data, f"Missing {field} in EventEnvelope"

                # Validate event metadata
                assert envelope_data["event_type"] == "huleedu.file.essay.content.provisioned.v1", (
                    f"Unexpected event_type: {envelope_data['event_type']}"
                )

                # Validate EssayContentProvisionedV1 data
                content_data = envelope_data["data"]

                assert content_data["batch_id"] == batch_id, (
                    f"Event batch_id {content_data['batch_id']} doesn't match expected {batch_id}"
                )
                assert content_data["original_file_name"] == test_file_path.name, (
                    f"Unexpected filename: {content_data['original_file_name']}"
                )

                required_content_fields = ["text_storage_id", "file_size_bytes"]
                for field in required_content_fields:
                    assert field in content_data, f"Missing {field} in content data"
                    assert content_data[field], f"Empty {field} in content data"

                assert content_data["file_size_bytes"] > 0, "Invalid file_size_bytes"

                # Validate correlation ID matches
                event_correlation_id = envelope_data.get("correlation_id")
                data_correlation_id = content_data.get("correlation_id")

                correlation_match = False
                if ((event_correlation_id and event_correlation_id == upload_correlation_id) or
                    (data_correlation_id and data_correlation_id == upload_correlation_id)):
                    correlation_match = True

                assert correlation_match, (
                    f"No correlation ID match found. "
                    f"Upload: {upload_correlation_id}, "
                    f"Event: {event_correlation_id}, "
                    f"Data: {data_correlation_id}"
                )

                print("✅ EssayContentProvisionedV1 event validated")
                print(f"   Text storage ID: {content_data['text_storage_id']}")
                print(f"   File size: {content_data['file_size_bytes']} bytes")

            except Exception as e:
                pytest.fail(f"Event collection or validation failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_multiple_files_generate_multiple_events(self):
        """
        Test uploading multiple files generates multiple
        EssayContentProvisionedV1 events using utilities.

        Validates:
        - ServiceTestManager handles multiple file upload
        - KafkaTestManager collects multiple events
        - Each file generates a separate event with correct data
        """
        service_manager = ServiceTestManager()

        endpoints = await service_manager.get_validated_endpoints()
        if "file_service" not in endpoints:
            pytest.skip("File Service not available")

        test_file_paths = [Path("test_uploads/essay1.txt"), Path("test_uploads/essay2.txt")]
        for test_file in test_file_paths:
            if not test_file.exists():
                pytest.skip(f"Test file {test_file} not found")

        batch_id = f"e2e-multi-event-{uuid.uuid4().hex[:8]}"

        # Use KafkaTestManager for event monitoring
        topics = ["huleedu.file.essay.content.provisioned.v1"]
        async with kafka_event_monitor("multi_file_events_test", topics) as consumer:
            # Upload multiple files using ServiceTestManager utility
            files: list[dict[str, Any]] = []
            for test_file in test_file_paths:
                with open(test_file, "rb") as f:
                    files.append({"name": test_file.name, "content": f.read()})

            try:
                upload_result = await service_manager.upload_files(batch_id, files)
                upload_correlation_id = upload_result["correlation_id"]

                print(f"✅ Multi-file upload for batch {batch_id}")
                print(f"   Upload correlation ID: {upload_correlation_id}")

            except RuntimeError as e:
                pytest.fail(f"ServiceTestManager multi-file upload failed: {e}")

            # Collect events for all uploaded files using KafkaTestManager
            def event_filter(event_data: dict[str, Any]) -> bool:
                """Filter for our specific batch (matching batch_id)."""
                return "data" in event_data and event_data["data"].get("batch_id") == batch_id

            try:
                events = await kafka_manager.collect_events(
                    consumer,
                    expected_count=len(test_file_paths),
                    timeout_seconds=45,
                    event_filter=event_filter,
                )

                # Validate we got the expected number of events
                assert len(events) == len(test_file_paths), (
                    f"Expected {len(test_file_paths)} events, got {len(events)}"
                )

                # Extract event data for validation - using single EventEnvelope structure
                event_data_list = [event_info["data"]["data"] for event_info in events]

                # Validate each file generated an event
                uploaded_files = {
                    event_data["original_file_name"] for event_data in event_data_list
                }
                expected_files = {test_file.name for test_file in test_file_paths}
                assert uploaded_files == expected_files, (
                    f"File name mismatch. Expected: {expected_files}, Got: {uploaded_files}"
                )

                # Validate all events have same batch_id and unique storage IDs
                storage_ids = set()
                for i, event_data in enumerate(event_data_list):
                    assert event_data["batch_id"] == batch_id
                    assert event_data["text_storage_id"]  # Should exist

                    storage_id = event_data["text_storage_id"]
                    assert storage_id not in storage_ids, f"Duplicate storage_id: {storage_id}"
                    storage_ids.add(storage_id)

                    print(f"📨 Event #{i + 1}: {event_data['original_file_name']}")

                print(f"✅ All {len(test_file_paths)} files generated separate events correctly")

            except Exception as e:
                pytest.fail(f"Multi-file event collection or validation failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_kafka_connectivity_prerequisite(self):
        """
        Test Kafka connectivity prerequisite using KafkaTestManager.

        Validates:
        - KafkaTestManager can establish consumer connection
        - Consumer can subscribe to HuleEdu topics without errors
        - Basic Kafka infrastructure is working
        """
        # Use KafkaTestManager to validate Kafka connectivity
        test_topics = [
            "huleedu.file.essay.content.provisioned.v1",
            "huleedu.batch.essays.registered.v1",
        ]

        try:
            async with kafka_event_monitor("connectivity_test", test_topics) as consumer:
                # If we get here, Kafka connectivity is working
                assigned_partitions = consumer.assignment()

                print("✅ Kafka connectivity validated")
                print("   Consumer created successfully")
                print(f"   Assigned partitions: {len(assigned_partitions)}")

                # Test that consumer is positioned correctly (no errors)
                # Note: We don't expect any messages, just testing connectivity
                assert consumer is not None

        except Exception as e:
            pytest.fail(f"Kafka connectivity test failed: {e}")
