"""
Shared utilities for validation coordination end-to-end tests.

This module provides common configuration, helper functions, and imports
used across multiple validation coordination test scenarios.

The utilities support testing validation failure coordination workflow:
- File Service validation integration
- EssayValidationFailedV1 event publishing
- ELS validation failure handling
- BOS enhanced BatchEssaysReady events
- Pipeline progression with COMPLETED_WITH_FAILURES
"""

import asyncio
import json
import uuid
from typing import Any, Dict, List

import aiohttp
from aiokafka import AIOKafkaConsumer
from huleedu_service_libs.logging_utils import create_service_logger

# Configure logging for debugging
logger = create_service_logger("test.validation_coordination_e2e")

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
            "content": (
                f"This is valid essay number {i+1} with sufficient content for validation. " * 10
                + "It contains multiple sentences and meets the minimum length requirements. "
                + "The essay has meaningful content and proper "
                + "structure for testing validation coordination."
            ),
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
            logger.info(
                f"File upload result: Status {response.status}, {len(files)} files uploaded"
            )
            return result


async def setup_kafka_consumer(test_name: str) -> AIOKafkaConsumer:
    """Set up and start Kafka consumer with proper partition assignment for test monitoring."""
    consumer_group_id = f"validation_e2e_test_{test_name}_{uuid.uuid4().hex[:8]}"
    monitoring_topics = list(TOPICS.values())

    event_consumer = AIOKafkaConsumer(
        *monitoring_topics,
        bootstrap_servers=CONFIG["kafka_bootstrap_servers"],
        group_id=consumer_group_id,
        auto_offset_reset="latest",
        enable_auto_commit=False,
        value_deserializer=lambda x: json.loads(x.decode("utf-8")),
    )

    await event_consumer.start()
    logger.info(f"Consumer starting for test: {test_name}")

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

    return event_consumer
