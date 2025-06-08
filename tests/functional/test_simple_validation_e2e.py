"""
Simple End-to-End Test for Content Validation.

Tests that content validation failures publish EssayValidationFailedV1 events 
with appropriate error codes (EMPTY_CONTENT, CONTENT_TOO_SHORT).
"""

import json
import uuid
from datetime import datetime, timedelta

import aiohttp
import pytest
from aiokafka import AIOKafkaConsumer
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("test.simple_validation_e2e")

CONFIG = {
    "bos_url": "http://localhost:5001",
    "file_service_url": "http://localhost:7001",
    "kafka_bootstrap_servers": "localhost:9093",
}

TOPICS = {
    "validation_failed": "huleedu.file.essay.validation.failed.v1",
    "content_provisioned": "huleedu.file.essay.content.provisioned.v1",
}


@pytest.mark.asyncio
async def test_content_validation_failures_publish_events():
    """Test that content validation failures publish validation failure events with proper error codes."""

    # Create a small batch
    async with aiohttp.ClientSession() as session:
        batch_request = {
            "course_code": "SIMPLE",
            "class_designation": "E2E",
            "expected_essay_count": 3,
            "essay_instructions": "Simple test",
            "teacher_name": "Test Teacher",
        }

        async with session.post(
            f"{CONFIG['bos_url']}/v1/batches/register",
            json=batch_request,
        ) as response:
            assert response.status == 202
            result = await response.json()
            batch_id = result["batch_id"]

        logger.info(f"Created batch {batch_id}")

    # Create test files: 1 valid, 2 content validation failures
    files = [
        {
            "file_name": "valid_essay.txt",
            "content": "This is a valid essay with enough content to pass validation."
        },
        {
            "file_name": "invalid_essay_empty.txt",
            "content": ""  # This will trigger EMPTY_CONTENT validation failure
        },
        {
            "file_name": "invalid_essay_short.txt",
            "content": "Too short"  # This will trigger CONTENT_TOO_SHORT validation failure
        }
    ]

    # Start Kafka consumer
    consumer = AIOKafkaConsumer(
        TOPICS["validation_failed"],
        TOPICS["content_provisioned"],
        bootstrap_servers=CONFIG["kafka_bootstrap_servers"],
        auto_offset_reset="latest",
        group_id=f"simple_test_{uuid.uuid4().hex[:8]}",
        value_deserializer=lambda x: json.loads(x.decode("utf-8")),
    )

    events = []

    try:
        await consumer.start()
        logger.info("Started Kafka consumer")

        # Upload files
        async with aiohttp.ClientSession() as session:
            form_data = aiohttp.FormData()
            form_data.add_field("batch_id", batch_id)

            for file_info in files:
                form_data.add_field(
                    "files",
                    file_info["content"].encode("utf-8"),
                    filename=file_info["file_name"],
                    content_type="text/plain"
                )

            async with session.post(
                f"{CONFIG['file_service_url']}/v1/files/batch",
                data=form_data,
            ) as response:
                logger.info(f"File upload status: {response.status}")
                result = await response.json()
                logger.info(f"Upload result: {result}")

        # Collect events for 20 seconds
        end_time = datetime.now() + timedelta(seconds=20)

        async for msg in consumer:
            if datetime.now() > end_time:
                break

            events.append({
                "topic": msg.topic,
                "data": msg.value,
                "timestamp": datetime.now().isoformat()
            })

            logger.info(f"Received event on {msg.topic}: {json.dumps(msg.value, indent=2)}")

            # Stop when we have expected events (1 content + 2 validation failures)
            validation_failure_count = len(
                [e for e in events if e["topic"] == TOPICS["validation_failed"]]
            )
            content_provision_count = len(
                [e for e in events if e["topic"] == TOPICS["content_provisioned"]]
            )

            if validation_failure_count >= 2 and content_provision_count >= 1:
                logger.info("Received all expected events!")
                break

    finally:
        await consumer.stop()

    # Verify results
    validation_failure_events = [e for e in events if e["topic"] == TOPICS["validation_failed"]]
    content_provision_events = [e for e in events if e["topic"] == TOPICS["content_provisioned"]]

    logger.info(f"Total events: {len(events)}")
    logger.info(f"Validation failures: {len(validation_failure_events)}")
    logger.info(f"Content provisions: {len(content_provision_events)}")

    # Assert we got the expected events
    assert len(
        content_provision_events) >= 1, "Should have at least 1 content provision (valid essay)"
    assert len(
        validation_failure_events) >= 2, "Should have 2 validation failures (empty + short)"

    # Check that validation failure events have the expected error codes
    empty_content_failures = []
    content_too_short_failures = []

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

    assert len(
        empty_content_failures) >= 1, "Should have at least 1 EMPTY_CONTENT validation failure event"
    assert len(
        content_too_short_failures) >= 1, "Should have at least 1 CONTENT_TOO_SHORT validation failure event"

    logger.info("✅ Test passed: Content validation failures "
                "correctly publish appropriate validation failure events!")
