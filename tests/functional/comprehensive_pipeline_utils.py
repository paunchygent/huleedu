"""
Comprehensive Pipeline Testing Utilities

Specialized utilities for end-to-end pipeline orchestration testing.
Supports complex multi-phase pipeline monitoring with modern patterns.
"""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger

from common_core.event_enums import ProcessingEvent, topic_name
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager

logger = create_service_logger("test.comprehensive_pipeline")


# Pipeline-specific topics configuration (complete pipeline coverage)
PIPELINE_TOPICS = {
    "batch_essays_registered": topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
    "essay_content_provisioned": topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED),
    "essay_validation_failed": topic_name(ProcessingEvent.ESSAY_VALIDATION_FAILED),
    "batch_ready": topic_name(ProcessingEvent.BATCH_ESSAYS_READY),
    "batch_spellcheck_initiate": topic_name(ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND),
    "els_batch_phase_outcome": topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME),
    "essay_spellcheck_completed": topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
    "batch_cj_assessment_initiate": topic_name(
        ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND,
    ),
    "cj_assessment_completed": topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
}


def create_comprehensive_kafka_manager() -> KafkaTestManager:
    """Create KafkaTestManager configured for comprehensive pipeline testing."""
    return KafkaTestManager()


async def load_real_test_essays(max_essays: int = 25) -> list[Path]:
    """
    Load real student essays from test directory.

    Args:
        max_essays: Maximum number of essays to load

    Returns:
        List of essay file paths

    Raises:
        pytest.skip: If real test essays are not available
    """
    import pytest

    real_test_dir = Path("test_uploads/real_test_batch")
    if not real_test_dir.exists():
        pytest.skip("Real test batch directory not found")

    essay_files = list(real_test_dir.glob("*.txt"))
    if len(essay_files) < 2:
        pytest.skip("Need at least 2 real essays for comprehensive test")

    logger.info(f"📚 Found {len(essay_files)} real student essays")
    return essay_files[:max_essays]


async def register_comprehensive_batch(
    service_manager: ServiceTestManager,
    expected_essay_count: int,
    correlation_id: str | None = None,
    user=None,
) -> tuple[str, str]:
    """
    Register a batch specifically for comprehensive pipeline testing.

    CRITICAL: Enables CJ assessment to ensure full pipeline execution.
    Returns the actual correlation ID that will be used by the service for events.

    Args:
        service_manager: ServiceTestManager instance
        expected_essay_count: Number of essays to expect
        correlation_id: Original correlation ID to use throughout pipeline
        user: Authenticated test user

    Returns:
        tuple[str, str]: (batch_id, actual_correlation_id_for_events)
    """

    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    # Randomly select from available course codes to prevent idempotency collisions
    import random

    from common_core.domain_enums import CourseCode

    available_courses = [
        CourseCode.ENG5,
        CourseCode.ENG6,
        CourseCode.ENG7,
        CourseCode.SV1,
        CourseCode.SV2,
        CourseCode.SV3,
    ]
    selected_course = random.choice(available_courses)

    # Use ServiceTestManager's create_batch method for authentication
    batch_id, actual_correlation_id = await service_manager.create_batch(
        expected_essay_count=expected_essay_count,
        course_code=selected_course,
        user=user,
        correlation_id=correlation_id,
        enable_cj_assessment=True,  # Enable CJ assessment for full pipeline
    )

    logger.info(f"✅ Comprehensive batch registered: {batch_id} (CJ assessment enabled)")
    logger.info(f"🔗 Actual correlation ID for event monitoring: {actual_correlation_id}")
    return batch_id, actual_correlation_id


async def upload_real_essays(
    service_manager: ServiceTestManager,
    batch_id: str,
    essay_files: list[Path],
    correlation_id: str | None = None,
    user=None,
) -> dict[str, Any]:
    """
    Upload real student essays for comprehensive testing.

    Args:
        service_manager: ServiceTestManager instance
        batch_id: Target batch ID
        essay_files: List of essay file paths
        correlation_id: Optional correlation ID
        user: Authenticated test user

    Returns:
        File upload response
    """
    # Convert Path objects to the format expected by ServiceTestManager
    files_data = []
    for essay_file in essay_files:
        essay_content = essay_file.read_bytes()  # Use read_bytes for binary content
        files_data.append(
            {"name": essay_file.name, "content": essay_content},
        )

    result = await service_manager.upload_files(
        batch_id=batch_id, files=files_data, user=user, correlation_id=correlation_id
    )
    logger.info(f"🚀 Uploaded {len(files_data)} real essays")
    return result


async def setup_pipeline_monitoring_first(kafka_manager: KafkaTestManager, test_name: str) -> Any:
    """
    Set up pipeline monitoring BEFORE triggering any actions.

    This prevents the race condition where events are published before the consumer
    is ready to read them. Follows the pattern from the original working test.

    Args:
        kafka_manager: KafkaTestManager instance
        test_name: Name for consumer group identification

    Returns:
        Active consumer context manager for pipeline monitoring
    """
    pipeline_topics = list(PIPELINE_TOPICS.values())

    # Start consumer and wait for proper positioning BEFORE any actions
    return kafka_manager.consumer(test_name, pipeline_topics)


async def watch_pipeline_progression_with_consumer(
    consumer,
    batch_id: str,
    correlation_id: str,
    expected_essay_count: int,
    timeout_seconds: int = 180,
) -> dict[str, Any] | None:
    """
    Watch complete pipeline progression with dynamic essay count.

    Args:
        consumer: Kafka consumer
        batch_id: Batch identifier
        correlation_id: Correlation identifier for event filtering
        expected_essay_count: Number of essays expected (dynamic)
        timeout_seconds: Maximum wait time

    Returns:
        Final completion event data or None if timeout
    """
    start_time = asyncio.get_event_loop().time()
    end_time = start_time + timeout_seconds

    # Track complete pipeline progression
    spellcheck_completions = 0
    content_provisioned_count = 0
    validation_failure_count = 0

    while asyncio.get_event_loop().time() < end_time:
        try:
            msg_batch = await consumer.getmany(timeout_ms=1000, max_records=10)

            for topic_partition, messages in msg_batch.items():
                for message in messages:
                    try:
                        # PRODUCTION FIDELITY: Handle raw bytes like real services
                        if isinstance(message.value, bytes):
                            raw_message = message.value.decode("utf-8")
                        else:
                            raw_message = message.value

                        # Parse JSON manually like real services
                        envelope_data = json.loads(raw_message)
                        event_data = envelope_data.get("data", {})
                        event_correlation_id = envelope_data.get("correlation_id")

                        # Primary filter: correlation_id MUST match
                        if correlation_id is None or event_correlation_id != correlation_id:
                            continue

                        # Secondary check: entity_id should match for batch-level events
                        entity_match = False

                        # List of topics that are about the whole batch
                        batch_level_topics = [
                            PIPELINE_TOPICS["batch_essays_registered"],
                            PIPELINE_TOPICS["batch_ready"],
                            PIPELINE_TOPICS["batch_spellcheck_initiate"],
                            PIPELINE_TOPICS["els_batch_phase_outcome"],
                            PIPELINE_TOPICS["batch_cj_assessment_initiate"],
                            PIPELINE_TOPICS["cj_assessment_completed"],
                        ]

                        if message.topic in batch_level_topics:
                            entity_id_from_event = None
                            if (
                                message.topic == PIPELINE_TOPICS["batch_essays_registered"]
                                or message.topic == PIPELINE_TOPICS["batch_ready"]
                            ):
                                entity_id_from_event = event_data.get("batch_id")
                            elif message.topic == PIPELINE_TOPICS["els_batch_phase_outcome"]:
                                # For correlation-matched events, we trust the correlation_id match
                                entity_match = True
                            else:
                                entity_id_from_event = event_data.get("entity_ref", {}).get(
                                    "entity_id",
                                )

                            if not entity_match and entity_id_from_event == batch_id:
                                entity_match = True
                        elif message.topic in [
                            PIPELINE_TOPICS["essay_spellcheck_completed"],
                            PIPELINE_TOPICS["essay_content_provisioned"],
                            PIPELINE_TOPICS["essay_validation_failed"],
                        ]:
                            # Essay-level events - correlation_id match is sufficient
                            entity_match = True
                        else:
                            # Skip topics not relevant to this test's flow
                            continue

                        if entity_match:
                            if message.topic == PIPELINE_TOPICS["batch_essays_registered"]:
                                essay_slots = len(event_data.get("essay_ids", []))
                                print(f"📝 Batch registration: {essay_slots} essay slots created")
                            elif message.topic == PIPELINE_TOPICS["essay_content_provisioned"]:
                                content_provisioned_count += 1
                                if content_provisioned_count == 1:
                                    print(
                                        "📨 0️⃣ File Service publishing content "
                                        "provisioned events...",
                                    )
                                elif content_provisioned_count == expected_essay_count:
                                    print(
                                        f"📨 0️⃣ All {content_provisioned_count} essays content "
                                        "provisioned - ELS will aggregate",
                                    )
                            elif message.topic == PIPELINE_TOPICS["essay_validation_failed"]:
                                validation_failure_count += 1
                                if validation_failure_count == 1:
                                    print("⚠️ Essay validation failures detected...")
                                essay_file = event_data.get("essay_file_name", "unknown")
                                reason = event_data.get("validation_error_reason", "unknown")
                                print(f"❌ Validation failed: {essay_file} ({reason})")
                            elif message.topic == PIPELINE_TOPICS["batch_ready"]:
                                ready_essays = event_data.get("ready_essays", [])
                                validation_failures = event_data.get("validation_failures", [])
                                ready_count = len(ready_essays) if ready_essays else 0
                                failed_count = (
                                    len(validation_failures) if validation_failures else 0
                                )
                                total_processed = ready_count + failed_count
                                print(
                                    f"📨 1️⃣ ELS published BatchEssaysReady: {ready_count} ready, "
                                    f"{failed_count} failed ({total_processed} total)",
                                )
                            elif message.topic == PIPELINE_TOPICS["batch_spellcheck_initiate"]:
                                essays_to_process = event_data.get("essays_to_process", [])
                                essay_count = len(essays_to_process) if essays_to_process else 0
                                print(
                                    f"📨 2️⃣ BOS published spellcheck initiate command: "
                                    f"{essay_count} essays",
                                )
                            elif message.topic == PIPELINE_TOPICS["essay_spellcheck_completed"]:
                                spellcheck_completions += 1
                                if spellcheck_completions == 1:
                                    print("📨 📝 Spell checker processing essays...")
                            elif message.topic == PIPELINE_TOPICS["els_batch_phase_outcome"]:
                                phase_name = event_data.get("phase_name")
                                phase_status = event_data.get("phase_status")
                                if phase_name == "spellcheck":
                                    print(
                                        f"📨 3️⃣ ELS published phase outcome: "
                                        f"{phase_name} -> {phase_status}",
                                    )
                                    completion_statuses = [
                                        "completed_successfully",
                                        "completed_with_failures",
                                    ]
                                    if phase_status in completion_statuses:
                                        print(
                                            "✅ Spellcheck phase completed! "
                                            "BOS will initiate CJ assessment...",
                                        )
                                elif phase_name == "cj_assessment":
                                    print(
                                        f"📨 6️⃣ ELS published phase outcome: "
                                        f"{phase_name} -> {phase_status}",
                                    )
                                    completion_statuses = [
                                        "completed_successfully",
                                        "completed_with_failures",
                                    ]
                                    if phase_status in completion_statuses:
                                        print(
                                            "🎯 Pipeline SUCCESS! "
                                            "Complete end-to-end processing finished.",
                                        )
                                        return dict(envelope_data)
                                else:
                                    print(
                                        f"📨 🔧 ELS published phase outcome: "
                                        f"{phase_name} -> {phase_status}",
                                    )
                            elif message.topic == PIPELINE_TOPICS["batch_cj_assessment_initiate"]:
                                essays_to_assess_list = event_data.get("essays_to_process", [])
                                essays_to_assess = (
                                    len(essays_to_assess_list) if essays_to_assess_list else 0
                                )
                                print(
                                    f"📨 4️⃣ BOS published CJ assessment initiate command: "
                                    f"{essays_to_assess} essays",
                                )
                            elif message.topic == PIPELINE_TOPICS["cj_assessment_completed"]:
                                rankings = event_data.get("rankings", [])
                                ranking_count = len(rankings) if rankings else 0
                                print(
                                    f"📨 5️⃣ CJ assessment completed: {ranking_count} essays ranked",
                                )
                                # Pipeline continues - ELS will publish final phase outcome

                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse pipeline message: {e}")
                        continue

            await asyncio.sleep(0.5)

        except Exception as e:
            logger.warning(f"Error polling for pipeline progression: {e}")
            await asyncio.sleep(1)

    logger.error(f"Pipeline did not complete within {timeout_seconds} seconds")
    return None
