"""
E2E Pipeline Test - Step 2: Event Monitoring

Tests monitoring of Kafka events published by File Service after file upload.
This validates that our pattern-aligned services publish events correctly
and that we can observe the event-driven workflow.

No mocking - tests real services and Kafka events only.
"""

import asyncio
import json
import uuid
from pathlib import Path

import httpx
import pytest
from aiokafka import AIOKafkaConsumer


class TestE2EStep2EventMonitoring:
    """
    Test event monitoring for File Service workflow.
    This validates the event-driven architecture after file upload.
    """

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_file_upload_publishes_content_provisioned_event(self):
        """
        Test that File Service publishes EssayContentProvisionedV1 event after file upload.

        Validates:
        - File Service publishes to correct Kafka topic
        - Event contains expected data structure
        - Event correlation_id matches upload correlation_id
        - Text storage ID is included for downstream processing
        """
        # Start Kafka consumer first to catch events
        consumer = AIOKafkaConsumer(
            "huleedu.file.essay.content.provisioned.v1",
            bootstrap_servers="localhost:9093",
            auto_offset_reset="latest",  # Only read new messages
            group_id=f"e2e-test-{uuid.uuid4().hex[:8]}",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            # Additional config to handle container networking
            client_id=f"e2e-test-client-{uuid.uuid4().hex[:8]}",
            fetch_max_wait_ms=1000,
            max_poll_records=10
        )

        try:
            await consumer.start()

            # Upload file to trigger event
            async with httpx.AsyncClient() as client:
                test_file_path = Path("test_uploads/essay1.txt")
                batch_id = f"e2e-event-test-{uuid.uuid4().hex[:8]}"

                with open(test_file_path, "rb") as f:
                    files = {"files": (test_file_path.name, f, "text/plain")}
                    data = {"batch_id": batch_id}

                    upload_response = await client.post(
                        "http://localhost:7001/v1/files/batch",
                        files=files,
                        data=data,
                        timeout=30.0
                    )

                    assert upload_response.status_code == 202, (
                        f"File upload failed: {upload_response.status_code}"
                    )

                    upload_data = upload_response.json()
                    upload_correlation_id = upload_data["correlation_id"]

                    print(f"✅ File uploaded for batch {batch_id}")
                    print(f"   Upload correlation ID: {upload_correlation_id}")

            # Wait for and validate event
            event_received = False
            timeout_seconds = 30

            try:
                async with asyncio.timeout(timeout_seconds):
                    async for message in consumer:
                        event_data = message.value

                        print(f"📨 Received Kafka event: {json.dumps(event_data, indent=2)}")

                        # Validate event structure - check if it's from our test
                        if ("data" in event_data and
                            event_data["data"].get("batch_id") == batch_id):

                            # Validate EventEnvelope structure
                            assert "event_id" in event_data, "Missing event_id in EventEnvelope"
                            assert "event_type" in event_data, "Missing event_type in EventEnvelope"
                            assert "source_service" in event_data, (
                                "Missing source_service in EventEnvelope"
                            )
                            assert "data" in event_data, "Missing data in EventEnvelope"

                            # Validate event metadata
                            assert event_data["event_type"] == (
                                "huleedu.file.essay.content.provisioned.v1"
                            ), (
                                f"Unexpected event_type: {event_data['event_type']}"
                            )
                            assert event_data["source_service"] == "file-service", (
                                f"Unexpected source_service: {event_data['source_service']}"
                            )

                            # Validate EssayContentProvisionedV1 data
                            content_data = event_data["data"]

                            assert content_data["batch_id"] == batch_id, (
                                f"Event batch_id {content_data['batch_id']} doesn't match "
                                f"expected {batch_id}"
                            )
                            assert content_data["original_file_name"] == test_file_path.name, (
                                f"Unexpected filename: {content_data['original_file_name']}"
                            )
                            assert "text_storage_id" in content_data, "Missing text_storage_id"
                            assert content_data["text_storage_id"], "Empty text_storage_id"
                            assert "file_size_bytes" in content_data, "Missing file_size_bytes"
                            assert content_data["file_size_bytes"] > 0, "Invalid file_size_bytes"

                            # Validate correlation ID matches - check both event level
                            # and data level
                            event_correlation_id = event_data.get("correlation_id")
                            data_correlation_id = content_data.get("correlation_id")

                            if event_correlation_id:
                                assert event_correlation_id == upload_correlation_id, (
                                    f"Event level correlation_id {event_correlation_id} "
                                    f"doesn't match upload {upload_correlation_id}"
                                )
                            elif data_correlation_id:
                                assert data_correlation_id == upload_correlation_id, (
                                    f"Data level correlation_id {data_correlation_id} "
                                    f"doesn't match upload {upload_correlation_id}"
                                )

                            print("✅ EssayContentProvisionedV1 event validated")
                            print(f"   Text storage ID: {content_data['text_storage_id']}")
                            print(f"   File size: {content_data['file_size_bytes']} bytes")

                            event_received = True
                            break

            except asyncio.TimeoutError:
                pytest.fail(
                    f"No EssayContentProvisionedV1 event received within "
                    f"{timeout_seconds} seconds"
                )

            assert event_received, "Expected event was not received"

        except Exception as e:
            pytest.fail(f"Kafka consumer setup failed: {e}")
        finally:
            await consumer.stop()

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_multiple_files_generate_multiple_events(self):
        """
        Test that uploading multiple files generates multiple EssayContentProvisionedV1 events.

        Validates:
        - Each file generates a separate event
        - All events have the same batch_id
        - All events have the same correlation_id
        - Events contain different text_storage_id values
        """
        consumer = AIOKafkaConsumer(
            "huleedu.file.essay.content.provisioned.v1",
            bootstrap_servers="localhost:9093",
            auto_offset_reset="latest",
            group_id=f"e2e-multi-test-{uuid.uuid4().hex[:8]}",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            client_id=f"e2e-multi-client-{uuid.uuid4().hex[:8]}",
            fetch_max_wait_ms=1000,
            max_poll_records=10
        )

        try:
            await consumer.start()

            # Upload multiple files
            test_files = [
                Path("test_uploads/essay1.txt"),
                Path("test_uploads/essay2.txt")
            ]
            batch_id = f"e2e-multi-event-{uuid.uuid4().hex[:8]}"

            async with httpx.AsyncClient() as client:
                files = []
                for test_file in test_files:
                    with open(test_file, "rb") as f:
                        files.append(("files", (test_file.name, f.read(), "text/plain")))

                data = {"batch_id": batch_id}

                upload_response = await client.post(
                    "http://localhost:7001/v1/files/batch",
                    files=files,
                    data=data,
                    timeout=30.0
                )

                assert upload_response.status_code == 202
                upload_data = upload_response.json()
                upload_correlation_id = upload_data["correlation_id"]

                print(f"✅ {len(test_files)} files uploaded for batch {batch_id}")

            # Collect events for all files
            events_received = []
            expected_file_count = len(test_files)
            timeout_seconds = 30

            try:
                async with asyncio.timeout(timeout_seconds):
                    async for message in consumer:
                        event_data = message.value

                        # Check if this event is from our test batch
                        if ("data" in event_data and
                            event_data["data"].get("batch_id") == batch_id):

                            events_received.append(event_data)
                            print(f"📨 Event {len(events_received)}/{expected_file_count} received")

                            # Stop when we have all expected events
                            if len(events_received) >= expected_file_count:
                                break

            except asyncio.TimeoutError:
                pytest.fail(
                    f"Only received {len(events_received)}/{expected_file_count} events "
                    f"within {timeout_seconds} seconds"
                )

            # Validate all events
            assert len(events_received) == expected_file_count, (
                f"Expected {expected_file_count} events, received {len(events_received)}"
            )

            text_storage_ids = []
            filenames = []

            for event_data in events_received:
                content_data = event_data["data"]

                # All events should have same batch_id and correlation_id
                assert content_data["batch_id"] == batch_id
                assert content_data["correlation_id"] == upload_correlation_id

                # Collect unique identifiers
                text_storage_ids.append(content_data["text_storage_id"])
                filenames.append(content_data["original_file_name"])

            # Validate uniqueness
            assert len(set(text_storage_ids)) == expected_file_count, (
                "text_storage_id values should be unique for each file"
            )

            # Validate all expected filenames are present
            expected_filenames = [f.name for f in test_files]
            assert set(filenames) == set(expected_filenames), (
                f"Received filenames {filenames} don't match expected {expected_filenames}"
            )

            print(f"✅ All {expected_file_count} events validated successfully")
            print(f"   Unique storage IDs: {len(set(text_storage_ids))}")

        finally:
            await consumer.stop()


# Helper function to check Kafka connectivity
@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.asyncio
async def test_kafka_connectivity_prerequisite():
    """
    Prerequisite test: Verify Kafka is accessible before running event monitoring tests.
    """
    consumer = AIOKafkaConsumer(
        "huleedu.file.essay.content.provisioned.v1",
        bootstrap_servers="localhost:9093",
        group_id=f"connectivity-test-{uuid.uuid4().hex[:8]}",
        auto_offset_reset="latest",
        client_id=f"connectivity-test-client-{uuid.uuid4().hex[:8]}",
        fetch_max_wait_ms=1000
    )

    try:
        await consumer.start()
        print("✅ Kafka connectivity confirmed - ready for event monitoring tests")

    except Exception as e:
        pytest.fail(
            f"Kafka not accessible: {e}\n"
            "Ensure Kafka is running: docker compose up -d"
        )
    finally:
        await consumer.stop()
