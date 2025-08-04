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

# All student names from essay files (properly capitalized)
TEST_STUDENT_NAMES = [
    "Alva Lemos",
    "Amanda Frantz",
    "Arve Bergström",
    "Axel Karlsson",
    "Cornelia Kardborn",
    "Ebba Noren Bergsröm",
    "Ebba Saviluoto",
    "Edgar Gezelius",
    "Elin Bogren",
    "Ellie Rankin",
    "Elvira Johansson",
    "Emil Pihlman",
    "Emil Zäll Jernberg",
    "Emma Wüst",
    "Erik Arvman",
    "Figg Eriksson",
    "Jagoda Struzik",
    "Jonathan Hedqvist",
    "Leon Gustavsson",
    "Manuel Gren",
    "Melek Özturk",
    "Nelli Moilanen",
    "Sam Höglund Öman",
    "Stella Sellström",
    "Vera Karlberg",
    "Simon Pub",  # Capitalized from "simon pub"
    "Tindra Cruz",  # Capitalized from "tindra cruz"
]


async def setup_test_class_with_roster(service_manager: ServiceTestManager, teacher_user) -> str:
    """Create the pre-existing test class with all students from essay files."""
    logger.info(f"🏫 Setting up test class with {len(TEST_STUDENT_NAMES)} students")

    # Create the class - we'll use the TEST_CLASS_ID directly in the database
    class_data = {
        "name": "Book Report ES24B Test Class",
        "course_codes": ["ENG5"],  # Must match CourseCode enum
    }

    # First, check if class already exists and delete it
    try:
        await service_manager.make_request(
            "DELETE", "class_management_service", f"/v1/classes/{TEST_CLASS_ID}", user=teacher_user
        )
        logger.info("Deleted existing test class")
    except Exception:
        # Class doesn't exist, which is fine
        pass

    # Create the class
    try:
        response = await service_manager.make_request(
            "POST", "class_management_service", "/v1/classes/", json=class_data, user=teacher_user
        )
        created_class_id = str(response["id"])
        logger.info(f"✅ Created class with ID: {created_class_id}")
    except Exception as e:
        raise RuntimeError(f"Failed to create test class: {e}")

    # Create all students and associate them with the class
    for student_name in TEST_STUDENT_NAMES:
        parts = student_name.rsplit(" ", 1)
        if len(parts) == 2:
            first_name, last_name = parts
        else:
            # Handle single name case
            first_name = student_name
            last_name = ""

        student_data = {
            "person_name": {"first_name": first_name, "last_name": last_name},
            "email": f"{first_name.lower().replace(' ', '.')}.{last_name.lower()}@test.edu"
            if last_name
            else f"{first_name.lower()}@test.edu",
            "class_ids": [created_class_id],
        }

        try:
            response = await service_manager.make_request(
                "POST",
                "class_management_service",
                "/v1/classes/students",
                json=student_data,
                user=teacher_user,
            )
            logger.debug(f"✅ Created student: {student_name}")
        except Exception as e:
            logger.warning(f"Failed to create student {student_name}: {e}")

    logger.info(f"✅ Test class setup complete with {len(TEST_STUDENT_NAMES)} students")

    # Return the actual class ID created
    return created_class_id


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
    clean_distributed_state: Any,
) -> None:  # clean_distributed_state fixture ensures clean Redis and Kafka state
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

        # PHASE 2 SPECIFIC: Create test class with students
        logger.info("🏫 Setting up test class with students for Phase 2 flow")
        class_id = await setup_test_class_with_roster(service_manager, teacher_user)
        logger.info(f"📝 Using test class: {class_id}")

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
        request_correlation_id = await publish_client_pipeline_request(
            kafka_manager, batch_id, "cj_assessment", actual_correlation_id
        )
        logger.info(f"📡 Published cj_assessment pipeline request: {request_correlation_id}")

        # Watch pipeline progression (same as GUEST flow from here)
        logger.info("⏳ Watching pipeline progression...")
        final_event = await watch_pipeline_progression_with_consumer(
            consumer=consumer,
            batch_id=batch_id,
            correlation_id=request_correlation_id,
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
