"""
Validation Coordination E2E Tests - Partial Failure Scenarios.

Tests validation coordination workflows where some essays fail validation,
ensuring proper coordination and enhanced BatchEssaysReady events with
validation failure information.

Test Scenarios:
- 24/25 essays succeed validation → Single failure coordination
- 20/25 essays succeed validation → Multiple failure coordination
"""

import asyncio
import json

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
async def test_partial_validation_failures_24_of_25():
    """Test scenario: 24/25 essays pass validation → Coordination workflow."""

    # Test setup
    course_code = "VAL102"
    class_designation = "PartialFail_ValidationCoordination"
    essay_count = 25

    # Set up Kafka consumer using shared utility
    event_consumer = await setup_kafka_consumer("partial_24_of_25")

    try:
        # NOW trigger operations - consumer is guaranteed ready
        batch_id, correlation_id = await create_test_batch(course_code, class_designation, essay_count)

        # Create 24 successful + 1 failing file
        test_files = create_validation_test_files(success_count=24, failure_count=1)

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
                                f"🔴 VALIDATION FAILURE: {json.dumps(event_data, indent=2)}"
                            )
                        elif topic == TOPICS["content_provisioned"]:
                            logger.info(
                                f"✅ CONTENT PROVISIONED: {json.dumps(event_data, indent=2)}"
                            )
                        elif topic == TOPICS["batch_ready"]:
                            logger.info(
                                f"🎯 BATCH READY: {json.dumps(event_data, indent=2)}")

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
                                validation_failures.append(
                                    EssayValidationFailedV1(**event_data)
                                )

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

            # Check if we have all expected events (24 provisions + 1 failure + batch ready)
            if (
                batch_ready_event is not None
                and content_provisions == 24
                and len(validation_failures) == 1
            ):
                logger.info("All expected events collected, breaking early")
                break

        # Validate results
        assert len(validation_failures) == 1, (
            f"Expected 1 validation failure, got {len(validation_failures)}"
        )
        assert content_provisions == 24, (
            f"Expected 24 content provisions, got {content_provisions}"
        )
        assert batch_ready_event is not None, "Expected BatchEssaysReady event"
        assert len(batch_ready_event.ready_essays) == 24, (
            f"Expected 24 ready essays, got {len(batch_ready_event.ready_essays)}"
        )

        # Validate enhanced BatchEssaysReady with validation failure information
        assert batch_ready_event.validation_failures is not None, (
            "Expected validation failures in BatchEssaysReady, got "
            f"{batch_ready_event.validation_failures}"
        )
        assert len(batch_ready_event.validation_failures) == 1, (
            "Expected 1 validation failure in BatchEssaysReady, got "
            f"{len(batch_ready_event.validation_failures)}"
        )
        assert batch_ready_event.total_files_processed == 25, (
            "Expected total_files_processed=25, got "
            f"{batch_ready_event.total_files_processed}"
        )

        # Validate validation failure event details
        failure = validation_failures[0]
        assert failure.batch_id == batch_id
        assert failure.validation_error_code in [
            "EMPTY_CONTENT",
            "CONTENT_TOO_SHORT",
            "TEXT_EXTRACTION_FAILED",
        ]
        assert failure.file_size_bytes >= 0

        logger.info(
            "✅ PARTIAL FAILURE TEST (24/25): Success - Validation coordination workflow validated"
        )

    finally:
        await event_consumer.stop()


@pytest.mark.asyncio
async def test_multiple_validation_failures_20_of_25():
    """Test scenario: 20/25 essays pass validation → Multiple failures coordination."""

    # Test setup
    course_code = "VAL103"
    class_designation = "MultiFail_ValidationCoordination"
    essay_count = 25

    # Set up Kafka consumer using shared utility
    event_consumer = await setup_kafka_consumer("multiple_20_of_25")

    try:
        # NOW trigger operations - consumer is guaranteed ready
        batch_id, correlation_id = await create_test_batch(
            course_code, class_designation, essay_count
        )

        # Create 20 successful + 5 failing files
        test_files = create_validation_test_files(success_count=20, failure_count=5)

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
                                validation_failures.append(
                                    EssayValidationFailedV1(**event_data)
                                )

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

            # Check if we have all expected events (20 provisions + 5 failures + batch ready)
            if (
                batch_ready_event is not None
                and content_provisions == 20
                and len(validation_failures) == 5
            ):
                logger.info("All expected events collected, breaking early")
                break

        # Validate results
        assert len(validation_failures) == 5, (
            f"Expected 5 validation failures, got {len(validation_failures)}"
        )
        assert content_provisions == 20, (
            f"Expected 20 content provisions, got {content_provisions}"
        )
        assert batch_ready_event is not None, "Expected BatchEssaysReady event"
        assert len(batch_ready_event.ready_essays) == 20, (
            f"Expected 20 ready essays, got {len(batch_ready_event.ready_essays)}"
        )

        # Validate enhanced coordination information
        assert batch_ready_event.validation_failures is not None
        assert len(batch_ready_event.validation_failures) == 5
        assert batch_ready_event.total_files_processed == 25

        # Validate failure diversity (different error codes)
        error_codes = {failure.validation_error_code for failure in validation_failures}
        assert len(error_codes) >= 2, (
            f"Expected diverse error codes, got {error_codes}"
        )

        logger.info(
            "✅ MULTIPLE FAILURES TEST (20/25): Success - Multiple failure coordination validated"
        )

    finally:
        await event_consumer.stop()
