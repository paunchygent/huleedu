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

Modernized to use ServiceTestManager and KafkaTestManager patterns.
"""

from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger

from tests.utils.kafka_test_manager import KafkaTestManager, create_kafka_test_config
from tests.utils.service_test_manager import ServiceTestManager
from tests.utils.test_auth_manager import AuthTestManager

# Configure logging for debugging
logger = create_service_logger("test.validation_coordination_e2e")

# Event Topics for Validation Coordination
TOPICS: dict[str, str] = {
    "batch_registered": "huleedu.batch.essays.registered.v1",
    "content_provisioned": "huleedu.file.essay.content.provisioned.v1",
    "validation_failed": "huleedu.file.essay.validation.failed.v1",
    "batch_ready": "huleedu.els.batch.essays.ready.v1",
    "pipeline_progress": "huleedu.batch.pipeline.progress.updated.v1",
}

# Validation coordination timeouts
VALIDATION_TIMEOUTS = {
    "test_timeout": 180,  # 3 minutes total timeout for validation scenarios
    "event_wait_timeout": 45,  # 45 seconds for individual events
}

# Store the user globally for the validation tests
_validation_test_user = None

async def create_validation_batch(
    course_code: str,
    essay_count: int,
    user_id: str = "validation_test_user",
    essay_instructions: str = "Test validation coordination",
) -> tuple[str, str]:
    """
    Create a validation test batch using modern ServiceTestManager with authentication.

    Returns (batch_id, correlation_id).
    """
    global _validation_test_user

    # Initialize with authentication support
    auth_manager = AuthTestManager()
    service_manager = ServiceTestManager(auth_manager=auth_manager)
    test_user = auth_manager.create_test_user(name=user_id, email=f"{user_id}@test.com")

    # Store the user for later use in uploads
    _validation_test_user = test_user

    batch_id, correlation_id = await service_manager.create_batch(
        expected_essay_count=essay_count,
        course_code=course_code,
        user=test_user,
    )

    logger.info(f"✅ Created validation batch {batch_id} for {essay_count} essays")
    return batch_id, correlation_id


def create_validation_test_files(success_count: int, failure_count: int) -> list[dict[str, Any]]:
    """Create test files with specific success/failure patterns for validation testing."""
    files = []

    # Create successful files (valid content)
    for i in range(success_count):
        files.append(
            {
                "name": f"valid_essay_{i + 1:02d}.txt",
                "content": (
                    f"This is valid essay number {i + 1} with sufficient content for validation. "
                    * 10
                    + "It contains multiple sentences and meets the minimum length requirements. "
                    + "The essay has meaningful content and proper "
                    + "structure for testing validation coordination."
                ),
                "expected_outcome": "success",
            },
        )

    # Create failure files (various validation failure types)
    failure_types = [
        {"suffix": "empty", "content": "", "error_code": "EMPTY_CONTENT"},
        {"suffix": "too_short", "content": "Short", "error_code": "CONTENT_TOO_SHORT"},
        {"suffix": "whitespace", "content": "   \n\t  \n  ", "error_code": "EMPTY_CONTENT"},
    ]

    for i in range(failure_count):
        failure_type = failure_types[i % len(failure_types)]
        files.append(
            {
                "name": f"invalid_essay_{failure_type['suffix']}_{i + 1:02d}.txt",
                "content": failure_type["content"],
                "expected_outcome": "validation_failure",
                "expected_error_code": failure_type["error_code"],
            },
        )

    return files


async def upload_validation_files(batch_id: str, files: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Upload validation test files using ServiceTestManager with authentication.

    Args:
        batch_id: Target batch ID
        files: List of file dictionaries with 'name' and 'content' keys

    Returns:
        Upload response
    """
    global _validation_test_user

    # Initialize with authentication support
    auth_manager = AuthTestManager()
    service_manager = ServiceTestManager(auth_manager=auth_manager)

    # Use the same user that created the batch
    if _validation_test_user is None:
        # Fallback to default user if no user was stored
        test_user = auth_manager.get_default_user()
    else:
        test_user = _validation_test_user

    result = await service_manager.upload_files(
        batch_id=batch_id,
        files=files,
        user=test_user,
    )

    logger.info(f"✅ Uploaded {len(files)} validation test files to batch {batch_id}")
    return result


def create_validation_kafka_manager() -> KafkaTestManager:
    """
    Create KafkaTestManager configured for validation coordination testing.

    Returns configured KafkaTestManager instance.
    """
    # Create Kafka configuration with validation coordination topics
    kafka_config = create_kafka_test_config(
        bootstrap_servers="localhost:9093",
        topics=TOPICS,
        assignment_timeout=15,
    )

    return KafkaTestManager(kafka_config)
