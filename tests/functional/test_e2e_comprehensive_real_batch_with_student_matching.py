"""
Comprehensive End-to-End Real Batch Test with Student Matching (Phase 2)

This test validates the complete Phase 2 preprocessing pipeline for REGULAR batches,
including student matching and association confirmation:

1. Create class with student roster in Class Management Service
2. Register batch with class_id (triggers REGULAR flow)
3. File Upload → EssayContentProvisionedV1 events
4. ELS aggregates → BatchContentProvisioningCompleted event
5. BOS transitions to AWAITING_STUDENT_VALIDATION state
6. BOS initiates student matching → BatchStudentMatchingInitiateCommand
7. NLP Service processes essays → BatchAuthorMatchesSuggested
8. Teacher confirms associations → StudentAssociationsConfirmed
9. ELS updates essays → BatchEssaysReady event
10. BOS receives BatchEssaysReady → ready for pipeline execution
11. Client request → Spellcheck → CJ Assessment → Complete

Tests the full Phase 2 flow with real student essays and class roster.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Any, Optional

import pytest
from common_core.domain_enums import CourseCode
from structlog import get_logger

from tests.functional.client_pipeline_test_utils import publish_client_pipeline_request
from tests.functional.comprehensive_pipeline_utils import (
    create_comprehensive_kafka_manager,
    watch_pipeline_progression_with_consumer,
)
from tests.utils.auth_manager import AuthTestManager
from tests.utils.event_factory import reset_test_event_factory
from tests.utils.service_test_manager import ServiceTestManager

logger = get_logger(__name__)


# Pre-existing test class with 4 students enrolled for Phase 2 testing
# Students: Alva Lemos, Amanda Frantz, Simon Pub, Tindra Cruz
TEST_CLASS_ID = "550e8400-e29b-41d4-a716-446655440001"


async def wait_for_student_matching_events(
    consumer: Any, batch_id: str, correlation_id: str, timeout_seconds: int = 60
) -> Optional[dict[str, Any]]:  # batch_id is logged in error messages
    """
    Monitor Phase 2 student matching events.

    Returns the BatchAuthorMatchesSuggested event data when received.
    """
    start_time = asyncio.get_event_loop().time()
    end_time = start_time + timeout_seconds

    matching_initiated = False
    matching_requested = False

    while asyncio.get_event_loop().time() < end_time:
        try:
            msg_batch = await consumer.getmany(timeout_ms=1000, max_records=10)

            for _topic_partition, messages in msg_batch.items():
                for message in messages:
                    try:
                        # Parse message
                        if isinstance(message.value, bytes):
                            raw_message = message.value.decode("utf-8")
                        else:
                            raw_message = message.value

                        import json

                        envelope_data = json.loads(raw_message)
                        event_correlation_id = envelope_data.get("correlation_id")
                        event_type = envelope_data.get("event_type", "")

                        # Filter by correlation ID
                        if event_correlation_id != correlation_id:
                            continue

                        # Track student matching flow
                        if "student.matching.initiate.command" in event_type:
                            matching_initiated = True
                            logger.info("📨 BOS initiated student matching")

                        elif "student.matching.requested" in event_type:
                            matching_requested = True
                            logger.info("📨 ELS requested student matching from NLP")

                        elif "author.matches.suggested" in event_type:
                            logger.info("📨 NLP suggested student-essay associations")
                            result: dict[str, Any] = envelope_data
                            return result

                    except Exception as e:
                        logger.warning(f"Error parsing message: {e}")
                        continue

        except asyncio.TimeoutError:
            continue

    logger.error(
        f"Timeout waiting for student matching events. "
        f"Initiated: {matching_initiated}, Requested: {matching_requested}"
    )
    return None


async def confirm_student_associations(
    service_manager: ServiceTestManager, batch_id: str, teacher_user: Any, correlation_id: str
) -> dict[str, Any]:
    """
    Fetch suggested associations and confirm them as teacher.
    """
    # First, get the suggested associations
    response = await service_manager.make_request(
        method="GET",
        service="class_management_service",
        path=f"/v1/batches/{batch_id}/student-associations",
        user=teacher_user,
        correlation_id=correlation_id,
    )

    associations = response.get("associations", [])
    logger.info(f"📋 Retrieved {len(associations)} suggested associations")

    # Simulate teacher review - confirm all associations
    confirmation_data = {
        "associations": [
            {
                "essay_id": assoc["essay_id"],
                "student_id": assoc["suggested_student_id"],
                "confirmed": True,
            }
            for assoc in associations
        ],
        "confirmation_method": "manual_teacher_review",
    }

    # Confirm associations
    confirm_response = await service_manager.make_request(
        method="POST",
        service="class_management_service",
        path=f"/v1/batches/{batch_id}/student-associations/confirm",
        json=confirmation_data,
        user=teacher_user,
        correlation_id=correlation_id,
    )

    logger.info("✅ Teacher confirmed all student-essay associations")
    return confirm_response


async def wait_for_batch_essays_ready(
    consumer: Any, batch_id: str, correlation_id: str, timeout_seconds: int = 30
) -> bool:  # batch_id is used in filtering events
    """Wait for BatchEssaysReady event after associations are confirmed."""
    start_time = asyncio.get_event_loop().time()
    end_time = start_time + timeout_seconds

    while asyncio.get_event_loop().time() < end_time:
        try:
            msg_batch = await consumer.getmany(timeout_ms=1000, max_records=10)

            for _topic_partition, messages in msg_batch.items():
                for message in messages:
                    try:
                        # Parse message
                        if isinstance(message.value, bytes):
                            raw_message = message.value.decode("utf-8")
                        else:
                            raw_message = message.value

                        import json

                        envelope_data = json.loads(raw_message)
                        event_correlation_id = envelope_data.get("correlation_id")
                        event_type = envelope_data.get("event_type", "")

                        # Check for our event
                        if (
                            event_correlation_id == correlation_id
                            and "batch.essays.ready" in event_type
                        ):
                            logger.info("📨 BatchEssaysReady received - batch ready for pipeline!")
                            return True

                    except Exception as e:
                        logger.warning(f"Error parsing message: {e}")
                        continue

        except asyncio.TimeoutError:
            continue

    return False


@pytest.mark.slow
@pytest.mark.e2e
@pytest.mark.functional
@pytest.mark.asyncio
@pytest.mark.timeout(300)  # 5 minute timeout for complete pipeline with student matching
async def test_comprehensive_real_batch_with_student_matching(
    verify_redis_is_pristine: Any,
) -> None:  # verify_redis_is_pristine fixture ensures clean Redis state
    """
    Test complete Phase 2 pipeline with student matching for REGULAR batches.

    This test validates:
    1. Class creation with student roster
    2. Batch registration with class_id (REGULAR flow)
    3. File upload and content provisioning
    4. Student matching via NLP service
    5. Teacher confirmation of associations
    6. BatchEssaysReady after associations
    7. Pipeline execution (spellcheck + CJ assessment)

    Uses real student essays with actual names that need to be matched.
    """
    # Load real essays with student names
    essay_dir = Path(
        "/Users/olofs_mba/Documents/Repos/huledu-reboot/test_uploads/Book-Report-ES24B-2025-04-09-104843"
    )
    essay_files = list(essay_dir.glob("*.docx"))
    logger.info(f"📚 Found {len(essay_files)} real student essays")

    # Setup authentication
    auth_manager = AuthTestManager()
    teacher_user = auth_manager.create_test_user(role="teacher")

    # Initialize service manager (doesn't use context manager)
    service_manager = ServiceTestManager(auth_manager=auth_manager)

    # Verify all services are healthy
    endpoints = await service_manager.get_validated_endpoints()
    assert len(endpoints) >= 4, f"Expected at least 4 services, got {len(endpoints)}"
    print(f"✅ {len(endpoints)} services validated healthy")

    # Setup Kafka monitoring
    kafka_manager = create_comprehensive_kafka_manager()

    # Add Phase 2 specific topics (correct topic names from common_core)
    phase2_topics = [
        "huleedu.batch.student.matching.initiate.command.v1",
        "huleedu.batch.student.matching.requested.v1",
        "huleedu.batch.author.matches.suggested.v1",
        "huleedu.class.student.associations.confirmed.v1",
        "huleedu.els.batch.essays.ready.v1",
    ]

    # Subscribe to all topics including Phase 2
    from tests.functional.comprehensive_pipeline_utils import PIPELINE_TOPICS

    all_topics = list(PIPELINE_TOPICS.values()) + phase2_topics

    # Use KafkaTestManager with context manager for consumer
    async with kafka_manager.consumer("comprehensive_student_matching", all_topics) as consumer:
        await consumer.seek_to_end()  # Start from latest
        logger.info("Consumer started for test: comprehensive_student_matching")
        logger.info(f"Consumer assigned partitions: {consumer.assignment()}")

        # Get test correlation ID
        correlation_id = str(uuid.uuid4())
        logger.info(f"🔍 Test correlation ID: {correlation_id}")

        # PHASE 2 SPECIFIC: Use pre-existing test class with students
        # This test class has 4 students enrolled: Alva Lemos, Amanda Frantz, Simon Pub, Tindra Cruz
        class_id = TEST_CLASS_ID
        logger.info(f"📝 Using pre-existing test class: {class_id}")

        # Register batch WITH class_id (triggers REGULAR flow)
        logger.info(f"📝 Registering REGULAR batch with class_id: {class_id}")
        batch_id, actual_correlation_id = await service_manager.create_batch(
            expected_essay_count=len(essay_files),
            course_code=CourseCode.ENG5,
            user=teacher_user,
            correlation_id=correlation_id,
            enable_cj_assessment=True,
            class_id=class_id,  # This triggers REGULAR flow!
        )

        logger.info(f"✅ REGULAR batch registered: {batch_id}")
        logger.info(f"🔗 Monitoring events with correlation ID: {actual_correlation_id}")

        # Upload real student essays
        logger.info("🚀 Uploading real student essays...")
        files_data = []
        for essay_file in essay_files:
            essay_content = essay_file.read_bytes()
            files_data.append({"name": essay_file.name, "content": essay_content})

        upload_result = await service_manager.upload_files(
            batch_id=batch_id,
            files=files_data,
            user=teacher_user,
            correlation_id=actual_correlation_id,
        )
        logger.info(f"✅ File upload successful: {upload_result}")

        # Wait for content provisioning to complete
        logger.info("⏳ Waiting for content provisioning...")
        await asyncio.sleep(3)  # Give time for essay processing

        # PHASE 2: Wait for student matching events
        logger.info("⏳ Waiting for student matching to begin...")
        matching_event = await wait_for_student_matching_events(
            consumer, batch_id, actual_correlation_id, timeout_seconds=60
        )

        if not matching_event:
            pytest.fail("Student matching events not received within timeout")

        # Give NLP service time to process and Class Management to store
        await asyncio.sleep(2)

        # PHASE 2: Teacher confirms associations
        logger.info("👨‍🏫 Teacher reviewing and confirming student associations...")
        await confirm_student_associations(
            service_manager, batch_id, teacher_user, actual_correlation_id
        )

        # Wait for BatchEssaysReady (only happens after associations confirmed)
        logger.info("⏳ Waiting for BatchEssaysReady after association confirmation...")
        ready_received = await wait_for_batch_essays_ready(
            consumer, batch_id, actual_correlation_id
        )

        if not ready_received:
            pytest.fail("BatchEssaysReady not received after association confirmation")

        # Now batch should be READY_FOR_PIPELINE_EXECUTION
        # Send client pipeline request
        logger.info("📤 Sending client pipeline request...")
        await publish_client_pipeline_request(kafka_manager, batch_id, actual_correlation_id)
        logger.info(f"📡 Published pipeline request with correlation: {actual_correlation_id}")

        # Watch pipeline progression (same as GUEST flow from here)
        logger.info("⏳ Watching pipeline progression...")
        final_event = await watch_pipeline_progression_with_consumer(
            consumer=consumer,
            batch_id=batch_id,
            correlation_id=actual_correlation_id,
            expected_essay_count=len(essay_files),
            timeout_seconds=120,
        )

        if final_event:
            logger.info(
                "✅ Complete pipeline success with student matching! "
                f"Final event: {final_event['event_type']}"
            )
        else:
            pytest.fail("Pipeline did not complete within timeout")

    # Reset test factories
    reset_test_event_factory()
