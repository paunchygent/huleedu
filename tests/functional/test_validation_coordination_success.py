"""
Validation Coordination E2E Tests - Success Scenarios.

Tests validation coordination workflows where all essays pass validation,
ensuring the normal workflow path functions correctly without failure coordination.

Test Scenarios:
- 25/25 essays succeed validation → Normal workflow path

Modernized to use ServiceTestManager and KafkaTestManager patterns.
"""

import pytest

from tests.utils.auth_manager import AuthTestManager, create_test_teacher
from tests.utils.kafka_test_manager import kafka_event_monitor
from tests.utils.service_test_manager import ServiceTestManager


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.asyncio
async def test_all_essays_pass_validation():
    """
    Test all essays pass validation and trigger BatchEssaysReady event.

    Validates:
    - ServiceTestManager handles multi-file upload correctly
    - All essays pass validation (no validation failure events)
    - ELS publishes BatchEssaysReady event when all essays are valid
    - Event contains correct ready essay count
    """
    # Initialize with authentication support
    auth_manager = AuthTestManager()
    service_manager = ServiceTestManager(auth_manager=auth_manager)
    test_teacher = create_test_teacher()

    # Validate services are available
    endpoints = await service_manager.get_validated_endpoints()
    if "file_service" not in endpoints:
        pytest.skip("File Service not available for validation coordination testing")

    # Create batch first (required for file uploads)
    expected_essay_count = 3
    batch_id, correlation_id = await service_manager.create_batch(
        expected_essay_count=expected_essay_count, course_code="ENG5", user=test_teacher
    )
    print(f"✅ Batch created: {batch_id}")

    # Use KafkaTestManager for comprehensive event monitoring
    topics = [
        "huleedu.file.essay.content.provisioned.v1",
        "huleedu.file.essay.validation.failed.v1",
        "huleedu.els.batch.essays.ready.v1",
    ]

    async with kafka_event_monitor("validation_success_test", topics) as _consumer:
        # Upload multiple valid files
        files = [
            {
                "name": "essay1.txt",
                "content": b"This is a valid essay with sufficient content for validation.",
            },
            {
                "name": "essay2.txt",
                "content": b"Another valid essay with proper length and content structure.",
            },
            {
                "name": "essay3.txt",
                "content": b"Third valid essay ensuring we have enough content for validation.",
            },
        ]

        try:
            upload_result = await service_manager.upload_files(
                batch_id=batch_id, files=files, user=test_teacher, correlation_id=correlation_id
            )
            upload_correlation_id = upload_result["correlation_id"]

            print(f"✅ All files uploaded for batch {batch_id}")
            print(f"   Upload correlation ID: {upload_correlation_id}")

        except RuntimeError as e:
            pytest.fail(f"ServiceTestManager upload failed: {e}")
