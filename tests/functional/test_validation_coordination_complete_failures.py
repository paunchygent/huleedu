"""
Validation Coordination E2E Tests - Complete Failure Scenarios.

Tests validation coordination workflows for extreme failure scenarios,
ensuring proper handling of complete validation failures and timing constraints.

Test Scenarios:
- 0/25 essays succeed validation → Complete failure batch coordination
- Timing test → Ensures coordination prevents infinite waits
"""

import asyncio
import json
from datetime import datetime

import pytest

from common_core.events.batch_coordination_events import BatchEssaysReady
from common_core.events.file_events import EssayValidationFailedV1
from tests.functional.validation_coordination_utils import (
    TOPICS,
    create_test_batch,
    create_validation_test_files,
    logger,
    setup_kafka_consumer,
    upload_test_files,
)


@pytest.mark.asyncio
async def test_complete_validation_failure_0_of_25():
    """Test scenario: 0/25 essays pass validation → Complete failure batch."""

    # Test setup
    course_code = "VAL104"
    class_designation = "CompleteFailure_ValidationCoordination"
    essay_count = 25

    # Set up Kafka consumer using shared utility
    event_consumer = await setup_kafka_consumer("complete_failure_0_of_25")

    try:
        # NOW trigger operations - consumer is guaranteed ready
        batch_id, correlation_id = await create_test_batch(
            course_code, class_designation, essay_count)

        # Create all failing files
        test_files = create_validation_test_files(success_count=0, failure_count=25)

        # Upload files
        upload_result = await upload_test_files(batch_id, test_files)

        # Collect events using active polling (proven working pattern)
        validation_failures = []
        content_provisions = 0
        batch_ready_event = None

        collection_timeout = 45  # seconds
        collection_end_time = asyncio.get_event_loop().time() + collection_timeout

        logger.info("Starting active event collection...")
        while asyncio.get_event_loop().time() < collection_end_time:
            msg_batch = await event_consumer.getmany(timeout_ms=1000, max_records=10)

            for topic_partition, messages in msg_batch.items():
                for message in messages:
                    try:
                        event_data = message.value
                        topic = message.topic

                        # Log events for debugging
                        if topic == TOPICS["validation_failed"]:
                            logger.info(
                                f"🔴 VALIDATION FAILURE: {json.dumps(event_data, indent=2)}")
                        elif topic == TOPICS["content_provisioned"]:
                            logger.info(
                                f"✅ CONTENT PROVISIONED: {json.dumps(event_data, indent=2)}")
                        elif topic == TOPICS["batch_ready"]:
                            logger.info(f"🎯 BATCH READY: {json.dumps(event_data, indent=2)}")

                        # Extract events for our batch
                        if topic == TOPICS["validation_failed"]:
                            # Handle EventEnvelope format
                            if "data" in event_data and isinstance(event_data["data"], dict):
                                failure_data = event_data["data"]
                                if failure_data.get("batch_id") == batch_id:
                                    validation_failures.append(EssayValidationFailedV1(**failure_data))
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

            # Check if we have all expected events (0 provisions + 25 failures + batch ready)
            if batch_ready_event is not None and len(validation_failures) == 25:
                logger.info("All expected events collected, breaking early")
                break

        # Validate results
        assert len(validation_failures) == 25, \
            f"Expected 25 validation failures, got {len(validation_failures)}"
        assert content_provisions == 0, \
            f"Expected 0 content provisions, got {content_provisions}"
        assert batch_ready_event is not None, \
            "Expected BatchEssaysReady event even for complete failure"
        assert len(batch_ready_event.ready_essays) == 0, \
            f"Expected 0 ready essays, got {len(batch_ready_event.ready_essays)}"

        # Validate complete failure coordination
        assert batch_ready_event.validation_failures is not None
        assert len(batch_ready_event.validation_failures) == 25
        assert batch_ready_event.total_files_processed == 25

        logger.info(
            "✅ COMPLETE FAILURE TEST (0/25): Success - Complete failure coordination validated")

    finally:
        await event_consumer.stop()


@pytest.mark.asyncio
async def test_validation_coordination_timing():
    """Test that validation coordination prevents infinite waits within timeout."""

    # Test setup with shorter timeout for timing test
    course_code = "VAL105"
    class_designation = "Timing_ValidationCoordination"
    essay_count = 10

    # Set up Kafka consumer using shared utility
    event_consumer = await setup_kafka_consumer("timing_test")

    try:
        # Start timing and NOW trigger operations - consumer is guaranteed ready
        timing_start = datetime.now()
        batch_id, correlation_id = await create_test_batch(
            course_code, class_designation, essay_count)

        # Create mixed success/failure pattern
        test_files = create_validation_test_files(success_count=7, failure_count=3)

        # Upload files
        await upload_test_files(batch_id, test_files)

        # Collect events using active polling (proven working pattern)
        validation_failures = []
        content_provisions = 0
        batch_ready_event = None

        collection_timeout = 30  # seconds
        collection_end_time = asyncio.get_event_loop().time() + collection_timeout

        logger.info("Starting active event collection...")
        while asyncio.get_event_loop().time() < collection_end_time:
            msg_batch = await event_consumer.getmany(timeout_ms=1000, max_records=10)

            for topic_partition, messages in msg_batch.items():
                for message in messages:
                    try:
                        event_data = message.value
                        topic = message.topic

                        # Extract events for our batch
                        if topic == TOPICS["validation_failed"]:
                            # Handle EventEnvelope format
                            if "data" in event_data and isinstance(event_data["data"], dict):
                                failure_data = event_data["data"]
                                if failure_data.get("batch_id") == batch_id:
                                    validation_failures.append(
                                        EssayValidationFailedV1(**failure_data))
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

            # Check if we have all expected events (7 provisions + 3 failures + batch ready)
            if batch_ready_event is not None and content_provisions == 7 and len(
                    validation_failures) == 3:
                logger.info("All expected events collected, breaking early")
                break

        end_time = datetime.now()
        coordination_time = (end_time - timing_start).total_seconds()

        # Validate timing and coordination
        assert batch_ready_event is not None, "Batch coordination should complete within timeout"
        assert coordination_time < 30, (
            f"Coordination took {coordination_time:.2f}s, should be < 30s"
        )

        assert len(validation_failures) == 3
        assert content_provisions == 7
        assert len(batch_ready_event.ready_essays) == 7

        logger.info(
            f"✅ TIMING TEST: Coordination completed in {coordination_time:.2f}s (target: <30s)")

    finally:
        await event_consumer.stop()
