"""
Comprehensive Pipeline Testing Utilities

Specialized utilities for end-to-end pipeline orchestration testing.
Supports complex multi-phase pipeline monitoring with modern patterns.
"""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from huleedu_service_libs.logging_utils import create_service_logger

from common_core.enums import ProcessingEvent, topic_name
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager

logger = create_service_logger("test.comprehensive_pipeline")


# Pipeline-specific topics configuration (matching original working test exactly)
PIPELINE_TOPICS = {
    "batch_ready": topic_name(ProcessingEvent.BATCH_ESSAYS_READY),
    "batch_spellcheck_initiate": topic_name(ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND),
    "els_batch_phase_outcome": topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME),
    "essay_spellcheck_completed": topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
    "batch_cj_assessment_initiate": topic_name(ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND),
    "cj_assessment_completed": topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
}


def create_comprehensive_kafka_manager() -> KafkaTestManager:
    """Create KafkaTestManager configured for comprehensive pipeline testing."""
    return KafkaTestManager()


async def load_real_test_essays(max_essays: int = 25) -> List[Path]:
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
    correlation_id: Optional[str] = None
) -> str:
    """
    Register a batch specifically for comprehensive pipeline testing.
    
    CRITICAL: Enables CJ assessment to ensure full pipeline execution.
    Matches original test logic: uses and keeps the ORIGINAL correlation_id throughout.
    
    Args:
        service_manager: ServiceTestManager instance
        expected_essay_count: Number of essays to expect
        correlation_id: Original correlation ID to use throughout pipeline
        
    Returns:
        batch_id only (original correlation_id continues to be used for events)
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    # For comprehensive pipeline testing, we need to enable CJ assessment
    # Create the batch request manually to include enable_cj_assessment=True
    endpoints = await service_manager.get_validated_endpoints()
    bos_base_url = endpoints["batch_orchestrator_service"]["base_url"]

    batch_request = {
        "course_code": "ENG5",
        "class_designation": "E2E-Comprehensive-Test",
        "expected_essay_count": expected_essay_count,
        "essay_instructions": "Comprehensive pipeline test with CJ assessment enabled",
        "teacher_name": "Test Teacher - Comprehensive Pipeline",
        "enable_cj_assessment": True,  # CRITICAL: Enable CJ assessment for full pipeline
    }

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{bos_base_url}/v1/batches/register",
            json=batch_request,
            headers={"X-Correlation-ID": correlation_id}
        ) as response:
            if response.status != 202:
                error_text = await response.text()
                raise RuntimeError(f"Batch creation failed: {response.status} - {error_text}")

            result = await response.json()
            batch_id = result["batch_id"]

            logger.info(f"✅ Comprehensive batch registered: {batch_id} (CJ assessment enabled)")
            # Return only batch_id like original test - keep using original correlation_id for events
            return batch_id


async def upload_real_essays(
    service_manager: ServiceTestManager,
    batch_id: str,
    essay_files: List[Path],
    correlation_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Upload real student essays for comprehensive testing.

    Args:
        service_manager: ServiceTestManager instance
        batch_id: Target batch ID
        essay_files: List of essay file paths
        correlation_id: Optional correlation ID

    Returns:
        File upload response
    """
    # Convert Path objects to the format expected by ServiceTestManager
    files_data = []
    for essay_file in essay_files:
        essay_content = essay_file.read_text(encoding="utf-8")
        files_data.append({
            "name": essay_file.name,
            "content": essay_content,
            "content_type": "text/plain"
        })

    result = await service_manager.upload_files(batch_id, files_data, correlation_id)
    logger.info(f"🚀 Uploaded {len(files_data)} real essays")
    return result


async def setup_pipeline_monitoring_first(
    kafka_manager: KafkaTestManager,
    test_name: str
) -> Any:
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
    timeout_seconds: int = 180
) -> Optional[Dict[str, Any]]:
    """
    Watch pipeline progression using the EXACT logic from the working original test.
    """
    start_time = asyncio.get_event_loop().time()
    end_time = start_time + timeout_seconds

    # Track spellcheck completion progress
    spellcheck_completions = 0

    while asyncio.get_event_loop().time() < end_time:
        try:
            msg_batch = await consumer.getmany(timeout_ms=1000, max_records=10)

            for topic_partition, messages in msg_batch.items():
                for message in messages:
                    try:
                        # PRODUCTION FIDELITY: Handle raw bytes like real services
                        # Real services: raw_message = msg.value.decode("utf-8")
                        if isinstance(message.value, bytes):
                            raw_message = message.value.decode("utf-8")
                        else:
                            raw_message = message.value

                        # Parse JSON manually like real services
                        envelope_data = json.loads(raw_message)
                        event_data = envelope_data.get("data", {})
                        event_correlation_id = envelope_data.get("correlation_id")

                        # DEBUG: Log ELS batch phase outcome messages regardless of correlation ID
                        if message.topic == PIPELINE_TOPICS["els_batch_phase_outcome"]:
                            phase_name = event_data.get('phase_name')
                            phase_status = event_data.get('phase_status')
                            entity_id = event_data.get("entity_ref", {}).get("entity_id")
                            print(f"🔍 ELS BATCH PHASE OUTCOME: phase={phase_name}, status={phase_status}, entity_id={entity_id}, correlation_id={event_correlation_id}, expected_correlation={correlation_id}, expected_batch={batch_id}")

                        # Primary filter: correlation_id MUST match.
                        if correlation_id is None or event_correlation_id != correlation_id:
                            continue

                        # Secondary check: entity_id should match for batch-level events.
                        # For essay-level events, this check is skipped as we rely on correlation_id.
                        entity_match = False

                        # List of topics that are about the whole batch
                        batch_level_topics = [
                            PIPELINE_TOPICS["batch_ready"],
                            PIPELINE_TOPICS["batch_spellcheck_initiate"],
                            PIPELINE_TOPICS["els_batch_phase_outcome"],
                            PIPELINE_TOPICS["batch_cj_assessment_initiate"],
                            PIPELINE_TOPICS["cj_assessment_completed"],
                        ]

                        if message.topic in batch_level_topics:
                            entity_id_from_event = None
                            if message.topic == PIPELINE_TOPICS["batch_ready"]:
                                entity_id_from_event = event_data.get("batch_id")
                            elif message.topic == PIPELINE_TOPICS["els_batch_phase_outcome"]:
                                # ELS batch phase outcome may not have entity_ref.entity_id
                                # For correlation-matched events, we trust the correlation_id match
                                entity_match = True
                                print("🔍 ELS batch phase outcome - trusting correlation_id match")
                            else:
                                entity_id_from_event = event_data.get("entity_ref", {}).get("entity_id")

                            if not entity_match and entity_id_from_event == batch_id:
                                entity_match = True
                        elif message.topic == PIPELINE_TOPICS["essay_spellcheck_completed"]:
                            # This is an essay-level event. The correlation_id match is sufficient.
                            entity_match = True
                        else:
                            # Skip topics not relevant to this test's flow
                            continue

                        if entity_match:
                            if message.topic == PIPELINE_TOPICS["batch_ready"]:
                                essay_count = len(event_data.get("ready_essays", []))
                                print(f"📨 1️⃣ ELS published BatchEssaysReady: {essay_count} essays ready")
                            elif message.topic == PIPELINE_TOPICS["batch_spellcheck_initiate"]:
                                print("📨 2️⃣ BOS published spellcheck initiate command")
                            elif message.topic == PIPELINE_TOPICS["essay_spellcheck_completed"]:
                                # Count spellcheck completions - when we have enough, expect phase outcome
                                spellcheck_completions += 1
                                essay_id = event_data.get("entity_ref", {}).get("entity_id", "unknown")
                                corrections_made = event_data.get("corrections_made", 0)
                                print(f"📨 Essay spellcheck completed: {essay_id[:8]}... ({corrections_made} corrections) [{spellcheck_completions} total]")

                                # Debug summary when all essays complete
                                if spellcheck_completions == 25:
                                    print("🎯 ALL 25 ESSAYS COMPLETED SPELLCHECK! Expecting ELS to publish batch phase outcome next...")
                                elif spellcheck_completions > 25:
                                    print(f"⚠️ More than 25 essays completed? Count: {spellcheck_completions}")
                            elif message.topic == PIPELINE_TOPICS["els_batch_phase_outcome"]:
                                phase_name = event_data.get('phase_name')
                                phase_status = event_data.get('phase_status')
                                print(f"📨 3️⃣ ELS published phase outcome: {phase_name} -> {phase_status}")
                                # If spellcheck phase completed (successfully or with failures), expect CJ assessment next
                                if phase_name == "spellcheck" and phase_status in ["COMPLETED_SUCCESSFULLY", "COMPLETED_WITH_FAILURES"]:
                                    print("✅ Spellcheck phase completed! Waiting for CJ assessment initiate...")
                            elif message.topic == PIPELINE_TOPICS["batch_cj_assessment_initiate"]:
                                essay_count = len(event_data.get("essays_to_process", []))
                                print(f"📨 4️⃣ BOS published CJ assessment initiate command: {essay_count} essays")
                            elif message.topic == PIPELINE_TOPICS["cj_assessment_completed"]:
                                rankings = event_data.get("rankings", [])
                                print(f"📨 5️⃣ CJ assessment completed: {len(rankings)} essays ranked")
                                print("🎯 Pipeline SUCCESS! Complete end-to-end processing finished.")
                                return dict(envelope_data)

                    except (json.JSONDecodeError, KeyError) as e:
                        print(f"⚠️ Failed to parse message: {e}")
                        continue

            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"⚠️ Error polling for pipeline progression: {e}")
            await asyncio.sleep(1)

    print(f"⏰ Pipeline did not complete within {timeout_seconds} seconds")
    return None
