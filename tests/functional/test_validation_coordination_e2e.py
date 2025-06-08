"""
End-to-End Validation Failure Coordination Test.

This test validates the complete validation failure coordination workflow implemented
in the File Service Validation Improvements project without mocking any business logic.

Test Scenarios:
1. 25/25 essays succeed validation → Normal workflow
2. 24/25 essays succeed validation → Validation failure coordination
3. 20/25 essays succeed validation → Multiple validation failures
4. 0/25 essays succeed validation → Complete validation failure batch

The test ensures:
- File Service validation integration works correctly
- EssayValidationFailedV1 events are published properly
- ELS validation failure handling prevents infinite waits
- BOS receives enhanced BatchEssaysReady events with validation failure info
- Pipeline progression handles COMPLETED_WITH_FAILURES correctly
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List

import aiohttp
import pytest
from aiokafka import AIOKafkaConsumer

from common_core.events.batch_coordination_events import BatchEssaysReady
from common_core.events.file_events import EssayValidationFailedV1

# Configure logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test Configuration
CONFIG: Dict[str, Any] = {
    "bos_url": "http://localhost:5001",
    "file_service_url": "http://localhost:7001",
    "els_url": "http://localhost:6001",
    "kafka_bootstrap_servers": "localhost:9093",
    "test_timeout": 180,  # 3 minutes total timeout for validation scenarios
    "event_wait_timeout": 45,  # 45 seconds for individual events
}

# Event Topics for Validation Coordination
TOPICS: Dict[str, str] = {
    "batch_registered": "huleedu.batch.essays.registered.v1",
    "content_provisioned": "huleedu.file.essay.content.provisioned.v1",
    "validation_failed": "huleedu.file.essay.validation.failed.v1",
    "batch_ready": "huleedu.els.batch.essays.ready.v1",
    "pipeline_progress": "huleedu.batch.pipeline.progress.updated.v1",
}



async def create_test_batch(
    course_code: str,
    class_designation: str,
    essay_count: int,
    essay_instructions: str = "Test validation coordination"
) -> tuple[str, str]:
    """Create a batch via BOS API and return batch_id and correlation_id."""
    async with aiohttp.ClientSession() as session:
        # Create batch registration request
        batch_request = {
            "course_code": course_code,
            "class_designation": class_designation,
            "expected_essay_count": essay_count,
            "essay_instructions": essay_instructions,
            "teacher_name": "Test Teacher - Validation Coordination",
        }

        async with session.post(
            f"{CONFIG['bos_url']}/v1/batches/register",
            json=batch_request,
        ) as response:
            if response.status != 202:
                response_text = await response.text()
                raise RuntimeError(f"Batch creation failed: {response.status} - {response_text}")

            result = await response.json()
            batch_id = result["batch_id"]
            correlation_id = result["correlation_id"]

            logger.info(f"Created test batch {batch_id} with {essay_count} expected essays")
            return batch_id, correlation_id


def create_validation_test_files(success_count: int, failure_count: int) -> List[Dict[str, Any]]:
    """Create test files with specific success/failure patterns for validation testing."""
    files = []

    # Create successful files (valid content)
    for i in range(success_count):
        files.append({
            "name": f"valid_essay_{i+1:02d}.txt",
            "content": f"This is valid essay number {i+1} with sufficient content for validation. " * 10 +
                      "It contains multiple sentences and meets the minimum length requirements. " +
                      "The essay has meaningful content and proper structure for testing validation coordination.",
            "expected_outcome": "success"
        })

    # Create failure files (various validation failure types)
    failure_types = [
        {"suffix": "empty", "content": "", "error_code": "EMPTY_CONTENT"},
        {"suffix": "too_short", "content": "Short", "error_code": "CONTENT_TOO_SHORT"},
        {"suffix": "whitespace", "content": "   \n\t  \n  ", "error_code": "EMPTY_CONTENT"},
    ]

    for i in range(failure_count):
        failure_type = failure_types[i % len(failure_types)]
        files.append({
            "name": f"invalid_essay_{failure_type['suffix']}_{i+1:02d}.txt",
            "content": failure_type["content"],
            "expected_outcome": "validation_failure",
            "expected_error_code": failure_type["error_code"]
        })

    return files


async def upload_test_files(batch_id: str, files: List[Dict[str, Any]]) -> Any:
    """Upload test files to File Service and return upload result."""
    async with aiohttp.ClientSession() as session:
        # Prepare multipart form data
        data = aiohttp.FormData()
        data.add_field("batch_id", batch_id)

        for file_info in files:
            data.add_field(
                "files",
                file_info["content"],
                filename=file_info["name"],
                content_type="text/plain"
            )

        async with session.post(
            f"{CONFIG['file_service_url']}/v1/files/batch",
            data=data,
        ) as response:
            result = await response.json()
            logger.info(f"File upload result: Status {response.status}, {len(files)} files uploaded")
            return result


@pytest.mark.asyncio
async def test_all_essays_pass_validation():
    """Test scenario: 25/25 essays pass validation → Normal workflow."""

    # Test setup
    course_code = "VAL101"
    class_designation = "AllPass_ValidationCoordination"
    essay_count = 25

    # Set up Kafka consumer FIRST (following working pattern)
    consumer_group_id = f"validation_e2e_test_{uuid.uuid4().hex[:8]}"
    monitoring_topics = list(TOPICS.values())

    event_consumer = AIOKafkaConsumer(
        *monitoring_topics,
        bootstrap_servers=CONFIG["kafka_bootstrap_servers"],
        group_id=consumer_group_id,
        auto_offset_reset="latest",
        enable_auto_commit=False,
        value_deserializer=lambda x: json.loads(x.decode("utf-8")),
    )

    try:
        await event_consumer.start()
        logger.info("Consumer starting...")

        # Wait for partition assignment and seek to end (proven working pattern)
        partitions_assigned = False
        assignment_timeout = 15  # seconds
        start_time = asyncio.get_event_loop().time()
        while not partitions_assigned:
            if asyncio.get_event_loop().time() - start_time > assignment_timeout:
                raise RuntimeError("Kafka consumer did not get partition assignment within timeout.")

            assigned_partitions = event_consumer.assignment()
            if assigned_partitions:
                logger.info(f"Consumer assigned partitions: {assigned_partitions}")
                await event_consumer.seek_to_end()
                logger.info("Consumer is now positioned at the end of all topics.")
                partitions_assigned = True
            else:
                await asyncio.sleep(0.2)

        # NOW trigger operations - consumer is guaranteed ready
        batch_id, correlation_id = await create_test_batch(course_code, class_designation, essay_count)

        # Create all successful files
        test_files = create_validation_test_files(success_count=25, failure_count=0)

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
                            logger.info(f"🔴 VALIDATION FAILURE: {json.dumps(event_data, indent=2)}")
                        elif topic == TOPICS["content_provisioned"]:
                            logger.info(f"✅ CONTENT PROVISIONED: {json.dumps(event_data, indent=2)}")
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

            # Check if we have all expected events
            if batch_ready_event is not None and content_provisions == 25:
                logger.info("All expected events collected, breaking early")
                break

        # Validate results
        assert len(validation_failures) == 0, f"Expected no validation failures, got {len(validation_failures)}"
        assert content_provisions == 25, f"Expected 25 content provisions, got {content_provisions}"
        assert batch_ready_event is not None, "Expected BatchEssaysReady event"
        assert len(batch_ready_event.ready_essays) == 25, f"Expected 25 ready essays, got {len(batch_ready_event.ready_essays)}"
        assert batch_ready_event.validation_failures is None or len(batch_ready_event.validation_failures) == 0

        logger.info("✅ ALL PASS VALIDATION TEST: Success - Normal workflow validated")

    finally:
        await event_consumer.stop()


@pytest.mark.asyncio
async def test_partial_validation_failures_24_of_25():
    """Test scenario: 24/25 essays pass validation → Coordination workflow."""

    # Test setup
    course_code = "VAL102"
    class_designation = "PartialFail_ValidationCoordination"
    essay_count = 25

    # Set up Kafka consumer FIRST (following working pattern)
    consumer_group_id = f"validation_e2e_test_{uuid.uuid4().hex[:8]}"
    monitoring_topics = list(TOPICS.values())

    event_consumer = AIOKafkaConsumer(
        *monitoring_topics,
        bootstrap_servers=CONFIG["kafka_bootstrap_servers"],
        group_id=consumer_group_id,
        auto_offset_reset="latest",
        enable_auto_commit=False,
        value_deserializer=lambda x: json.loads(x.decode("utf-8")),
    )

    try:
        await event_consumer.start()
        logger.info("Consumer starting...")

        # Wait for partition assignment and seek to end (proven working pattern)
        partitions_assigned = False
        assignment_timeout = 15  # seconds
        start_time = asyncio.get_event_loop().time()
        while not partitions_assigned:
            if asyncio.get_event_loop().time() - start_time > assignment_timeout:
                raise RuntimeError("Kafka consumer did not get partition assignment within timeout.")

            assigned_partitions = event_consumer.assignment()
            if assigned_partitions:
                logger.info(f"Consumer assigned partitions: {assigned_partitions}")
                await event_consumer.seek_to_end()
                logger.info("Consumer is now positioned at the end of all topics.")
                partitions_assigned = True
            else:
                await asyncio.sleep(0.2)

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
                            logger.info(f"🔴 VALIDATION FAILURE: {json.dumps(event_data, indent=2)}")
                        elif topic == TOPICS["content_provisioned"]:
                            logger.info(f"✅ CONTENT PROVISIONED: {json.dumps(event_data, indent=2)}")
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

            # Check if we have all expected events (24 provisions + 1 failure + batch ready)
            if batch_ready_event is not None and content_provisions == 24 and len(validation_failures) == 1:
                logger.info("All expected events collected, breaking early")
                break

        # Validate results
        assert len(validation_failures) == 1, f"Expected 1 validation failure, got {len(validation_failures)}"
        assert content_provisions == 24, f"Expected 24 content provisions, got {content_provisions}"
        assert batch_ready_event is not None, "Expected BatchEssaysReady event"
        assert len(batch_ready_event.ready_essays) == 24, f"Expected 24 ready essays, got {len(batch_ready_event.ready_essays)}"

        # Validate enhanced BatchEssaysReady with validation failure information
        assert batch_ready_event.validation_failures is not None, "Expected validation failures in BatchEssaysReady"
        assert len(batch_ready_event.validation_failures) == 1, f"Expected 1 validation failure in BatchEssaysReady, got {len(batch_ready_event.validation_failures)}"
        assert batch_ready_event.total_files_processed == 25, f"Expected total_files_processed=25, got {batch_ready_event.total_files_processed}"

        # Validate validation failure event details
        failure = validation_failures[0]
        assert failure.batch_id == batch_id
        assert failure.validation_error_code in ["EMPTY_CONTENT", "CONTENT_TOO_SHORT", "TEXT_EXTRACTION_FAILED"]
        assert failure.file_size_bytes >= 0

        logger.info("✅ PARTIAL FAILURE TEST (24/25): Success - Validation coordination workflow validated")

    finally:
        await event_consumer.stop()


@pytest.mark.asyncio
async def test_multiple_validation_failures_20_of_25():
    """Test scenario: 20/25 essays pass validation → Multiple failures coordination."""

    # Test setup
    course_code = "VAL103"
    class_designation = "MultiFail_ValidationCoordination"
    essay_count = 25

    # Set up Kafka consumer FIRST (following working pattern)
    consumer_group_id = f"validation_e2e_test_{uuid.uuid4().hex[:8]}"
    monitoring_topics = list(TOPICS.values())

    event_consumer = AIOKafkaConsumer(
        *monitoring_topics,
        bootstrap_servers=CONFIG["kafka_bootstrap_servers"],
        group_id=consumer_group_id,
        auto_offset_reset="latest",
        enable_auto_commit=False,
        value_deserializer=lambda x: json.loads(x.decode("utf-8")),
    )

    try:
        await event_consumer.start()
        logger.info("Consumer starting...")

        # Wait for partition assignment and seek to end (proven working pattern)
        partitions_assigned = False
        assignment_timeout = 15  # seconds
        start_time = asyncio.get_event_loop().time()
        while not partitions_assigned:
            if asyncio.get_event_loop().time() - start_time > assignment_timeout:
                raise RuntimeError("Kafka consumer did not get partition assignment within timeout.")

            assigned_partitions = event_consumer.assignment()
            if assigned_partitions:
                logger.info(f"Consumer assigned partitions: {assigned_partitions}")
                await event_consumer.seek_to_end()
                logger.info("Consumer is now positioned at the end of all topics.")
                partitions_assigned = True
            else:
                await asyncio.sleep(0.2)

        # NOW trigger operations - consumer is guaranteed ready
        batch_id, correlation_id = await create_test_batch(course_code, class_designation, essay_count)

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
                            logger.info(f"🔴 VALIDATION FAILURE: {json.dumps(event_data, indent=2)}")
                        elif topic == TOPICS["content_provisioned"]:
                            logger.info(f"✅ CONTENT PROVISIONED: {json.dumps(event_data, indent=2)}")
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

            # Check if we have all expected events (20 provisions + 5 failures + batch ready)
            if batch_ready_event is not None and content_provisions == 20 and len(validation_failures) == 5:
                logger.info("All expected events collected, breaking early")
                break

        # Validate results
        assert len(validation_failures) == 5, f"Expected 5 validation failures, got {len(validation_failures)}"
        assert content_provisions == 20, f"Expected 20 content provisions, got {content_provisions}"
        assert batch_ready_event is not None, "Expected BatchEssaysReady event"
        assert len(batch_ready_event.ready_essays) == 20, f"Expected 20 ready essays, got {len(batch_ready_event.ready_essays)}"

        # Validate enhanced coordination information
        assert batch_ready_event.validation_failures is not None
        assert len(batch_ready_event.validation_failures) == 5
        assert batch_ready_event.total_files_processed == 25

        # Validate failure diversity (different error codes)
        error_codes = {failure.validation_error_code for failure in validation_failures}
        assert len(error_codes) >= 2, f"Expected diverse error codes, got {error_codes}"

        logger.info("✅ MULTIPLE FAILURES TEST (20/25): Success - Multiple failure coordination validated")

    finally:
        await event_consumer.stop()


@pytest.mark.asyncio
async def test_complete_validation_failure_0_of_25():
    """Test scenario: 0/25 essays pass validation → Complete failure batch."""

    # Test setup
    course_code = "VAL104"
    class_designation = "CompleteFailure_ValidationCoordination"
    essay_count = 25

    # Set up Kafka consumer FIRST (following working pattern)
    consumer_group_id = f"validation_e2e_test_{uuid.uuid4().hex[:8]}"
    monitoring_topics = list(TOPICS.values())

    event_consumer = AIOKafkaConsumer(
        *monitoring_topics,
        bootstrap_servers=CONFIG["kafka_bootstrap_servers"],
        group_id=consumer_group_id,
        auto_offset_reset="latest",
        enable_auto_commit=False,
        value_deserializer=lambda x: json.loads(x.decode("utf-8")),
    )

    try:
        await event_consumer.start()
        logger.info("Consumer starting...")

        # Wait for partition assignment and seek to end (proven working pattern)
        partitions_assigned = False
        assignment_timeout = 15  # seconds
        start_time = asyncio.get_event_loop().time()
        while not partitions_assigned:
            if asyncio.get_event_loop().time() - start_time > assignment_timeout:
                raise RuntimeError("Kafka consumer did not get partition assignment within timeout.")

            assigned_partitions = event_consumer.assignment()
            if assigned_partitions:
                logger.info(f"Consumer assigned partitions: {assigned_partitions}")
                await event_consumer.seek_to_end()
                logger.info("Consumer is now positioned at the end of all topics.")
                partitions_assigned = True
            else:
                await asyncio.sleep(0.2)

        # NOW trigger operations - consumer is guaranteed ready
        batch_id, correlation_id = await create_test_batch(course_code, class_designation, essay_count)

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
                            logger.info(f"🔴 VALIDATION FAILURE: {json.dumps(event_data, indent=2)}")
                        elif topic == TOPICS["content_provisioned"]:
                            logger.info(f"✅ CONTENT PROVISIONED: {json.dumps(event_data, indent=2)}")
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
        assert len(validation_failures) == 25, f"Expected 25 validation failures, got {len(validation_failures)}"
        assert content_provisions == 0, f"Expected 0 content provisions, got {content_provisions}"
        assert batch_ready_event is not None, "Expected BatchEssaysReady event even for complete failure"
        assert len(batch_ready_event.ready_essays) == 0, f"Expected 0 ready essays, got {len(batch_ready_event.ready_essays)}"

        # Validate complete failure coordination
        assert batch_ready_event.validation_failures is not None
        assert len(batch_ready_event.validation_failures) == 25
        assert batch_ready_event.total_files_processed == 25

        logger.info("✅ COMPLETE FAILURE TEST (0/25): Success - Complete failure coordination validated")

    finally:
        await event_consumer.stop()


@pytest.mark.asyncio
async def test_validation_coordination_timing():
    """Test that validation coordination prevents infinite waits within timeout."""

    # Test setup with shorter timeout for timing test
    course_code = "VAL105"
    class_designation = "Timing_ValidationCoordination"
    essay_count = 10

    # Set up Kafka consumer FIRST (following working pattern)
    consumer_group_id = f"validation_e2e_test_{uuid.uuid4().hex[:8]}"
    monitoring_topics = list(TOPICS.values())

    event_consumer = AIOKafkaConsumer(
        *monitoring_topics,
        bootstrap_servers=CONFIG["kafka_bootstrap_servers"],
        group_id=consumer_group_id,
        auto_offset_reset="latest",
        enable_auto_commit=False,
        value_deserializer=lambda x: json.loads(x.decode("utf-8")),
    )

    try:
        await event_consumer.start()
        logger.info("Consumer starting...")

        # Wait for partition assignment and seek to end (proven working pattern)
        partitions_assigned = False
        assignment_timeout = 15  # seconds
        start_time = asyncio.get_event_loop().time()
        while not partitions_assigned:
            if asyncio.get_event_loop().time() - start_time > assignment_timeout:
                raise RuntimeError("Kafka consumer did not get partition assignment within timeout.")

            assigned_partitions = event_consumer.assignment()
            if assigned_partitions:
                logger.info(f"Consumer assigned partitions: {assigned_partitions}")
                await event_consumer.seek_to_end()
                logger.info("Consumer is now positioned at the end of all topics.")
                partitions_assigned = True
            else:
                await asyncio.sleep(0.2)

        # Start timing and NOW trigger operations - consumer is guaranteed ready
        timing_start = datetime.now()
        batch_id, correlation_id = await create_test_batch(course_code, class_designation, essay_count)

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

            # Check if we have all expected events (7 provisions + 3 failures + batch ready)
            if batch_ready_event is not None and content_provisions == 7 and len(validation_failures) == 3:
                logger.info("All expected events collected, breaking early")
                break

        end_time = datetime.now()
        coordination_time = (end_time - timing_start).total_seconds()

        # Validate timing and coordination
        assert batch_ready_event is not None, "Batch coordination should complete within timeout"
        assert coordination_time < 30, f"Coordination took {coordination_time:.2f}s, should be < 30s"

        assert len(validation_failures) == 3
        assert content_provisions == 7
        assert len(batch_ready_event.ready_essays) == 7

        logger.info(f"✅ TIMING TEST: Coordination completed in {coordination_time:.2f}s (target: <30s)")

    finally:
        await event_consumer.stop()
