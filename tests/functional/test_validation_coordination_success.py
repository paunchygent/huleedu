"""
Validation Coordination E2E Tests - Success Scenarios.

Tests validation coordination workflows where all essays pass validation,
ensuring the normal workflow path functions correctly without failure coordination.

Test Scenarios:
- 25/25 essays succeed validation → Normal workflow path

Modernized to use ServiceTestManager and KafkaTestManager patterns.
"""

import asyncio
import json

import pytest

from common_core.events.batch_coordination_events import BatchEssaysReady
from common_core.events.file_events import EssayValidationFailedV1
from tests.functional.validation_coordination_utils import (
    TOPICS,
    VALIDATION_TIMEOUTS,
    create_validation_batch,
    create_validation_kafka_manager,
    create_validation_test_files,
    logger,
    upload_validation_files,
)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.docker
async def test_all_essays_pass_validation():
    """Test scenario: 25/25 essays pass validation → Normal workflow."""

    # Test setup
    course_code = "VAL101"
    class_designation = "AllPass_ValidationCoordination"
    essay_count = 25

    # Set up Kafka consumer using modern utility pattern
    kafka_manager = create_validation_kafka_manager()

    async with kafka_manager.consumer("all_pass") as consumer:
        # NOW trigger operations - consumer is guaranteed ready
        batch_id, correlation_id = await create_validation_batch(
            course_code, class_designation, essay_count
        )

        # Create all successful files
        test_files = create_validation_test_files(success_count=25, failure_count=0)

        # Upload files using modern utility
        _ = await upload_validation_files(batch_id, test_files)

        # Collect events using modern utility pattern with proper JSON handling
        validation_failures = []
        content_provisions = 0
        batch_ready_event = None

        collection_timeout = VALIDATION_TIMEOUTS["event_wait_timeout"]
        collection_end_time = asyncio.get_event_loop().time() + collection_timeout

        logger.info("Starting active event collection...")
        while asyncio.get_event_loop().time() < collection_end_time:
            msg_batch = await consumer.getmany(timeout_ms=1000, max_records=10)

            for topic_partition, messages in msg_batch.items():
                for message in messages:
                    try:
                        # Parse raw message bytes to JSON (like original legacy code)
                        raw_message = message.value
                        if isinstance(raw_message, bytes):
                            raw_message = raw_message.decode("utf-8")

                        event_data = (
                            json.loads(raw_message)
                            if isinstance(raw_message, str)
                            else raw_message
                        )
                        topic = message.topic

                        # Log events for debugging
                        if topic == TOPICS["validation_failed"]:
                            logger.info(
                                f"🔴 VALIDATION FAILURE: {json.dumps(event_data, indent=2)}"
                            )
                        elif topic == TOPICS["content_provisioned"]:
                            logger.info(
                                f"✅ CONTENT PROVISIONED: {json.dumps(event_data, indent=2)}"
                            )
                        elif topic == TOPICS["batch_ready"]:
                            logger.info(f"🎯 BATCH READY: {json.dumps(event_data, indent=2)}")

                        # Extract events for our batch
                        if topic == TOPICS["validation_failed"]:
                            # Handle EventEnvelope format
                            if "data" in event_data and isinstance(event_data["data"], dict):
                                failure_data = event_data["data"]
                                if failure_data.get("batch_id") == batch_id:
                                    validation_failures.append(
                                        EssayValidationFailedV1(**failure_data)
                                    )
                            # Handle direct event format
                            elif event_data.get("batch_id") == batch_id:
                                validation_failures.append(EssayValidationFailedV1(**event_data))

                        elif topic == TOPICS["content_provisioned"]:
                            # Handle EventEnvelope format
                            if "data" in event_data and isinstance(event_data["data"], dict):
                                provision_data = event_data["data"]
                                if provision_data.get("batch_id") == batch_id:
                                    content_provisions += 1
                            # Handle direct event format
                            elif event_data.get("batch_id") == batch_id:
                                content_provisions += 1

                        elif topic == TOPICS["batch_ready"]:
                            # Handle EventEnvelope format
                            if "data" in event_data and isinstance(event_data["data"], dict):
                                ready_data = event_data["data"]
                                if ready_data.get("batch_id") == batch_id:
                                    batch_ready_event = BatchEssaysReady(**ready_data)
                            # Handle direct event format
                            elif event_data.get("batch_id") == batch_id:
                                batch_ready_event = BatchEssaysReady(**event_data)

                    except Exception as e:
                        logger.error(f"Error processing event: {e}")

            # Check if we have all expected events
            if batch_ready_event is not None and content_provisions == 25:
                logger.info("All expected events collected, breaking early")
                break

        # Validate results
        assert len(validation_failures) == 0, (
            f"Expected no validation failures, got {len(validation_failures)}"
        )
        assert content_provisions == 25, f"Expected 25 content provisions, got {content_provisions}"
        assert batch_ready_event is not None, "Expected BatchEssaysReady event"
        assert len(batch_ready_event.ready_essays) == 25, (
            f"Expected 25 ready essays, got {len(batch_ready_event.ready_essays)}"
        )
        assert (
            batch_ready_event.validation_failures is None
            or len(batch_ready_event.validation_failures) == 0
        )

        logger.info("✅ ALL PASS VALIDATION TEST: Success - Normal workflow validated")
