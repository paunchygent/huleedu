"""
End-to-End NLP Pipeline Test with Student Matching

This test validates the complete NLP pipeline for REGULAR batches,
including student matching and NLP linguistic analysis:

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
11. Client request → Spellcheck → NLP Analysis → Complete

Tests the full NLP pipeline flow with real student essays and linguistic analysis.
"""

from pathlib import Path
from typing import Any

import pytest
from structlog import get_logger

from tests.functional.pipeline_test_harness import PipelineTestHarness
from tests.utils.auth_manager import AuthTestManager
from tests.utils.event_factory import reset_test_event_factory
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager

logger = get_logger(__name__)


@pytest.mark.slow
@pytest.mark.e2e
@pytest.mark.functional
@pytest.mark.asyncio
@pytest.mark.timeout(300)  # 5 minute timeout for complete pipeline with student matching
async def test_e2e_nlp_pipeline_with_student_matching(
    clean_distributed_state: Any,
) -> None:  # clean_distributed_state fixture ensures clean Redis and Kafka state
    """
    Test complete NLP pipeline with student matching for REGULAR batches.

    This test validates:
    1. Class creation with student roster
    2. Batch registration with class_id (REGULAR flow)
    3. File upload and content provisioning
    4. Student matching via NLP service
    5. Teacher confirmation of associations
    6. BatchEssaysReady after associations
    7. NLP pipeline execution (spellcheck + nlp analysis)

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

    # Initialize service manager
    service_manager = ServiceTestManager(auth_manager=auth_manager)

    # Verify all services are healthy
    endpoints = await service_manager.get_validated_endpoints()
    assert len(endpoints) >= 4, f"Expected at least 4 services, got {len(endpoints)}"
    logger.info(f"✅ {len(endpoints)} services validated healthy")

    # Setup Kafka manager
    kafka_manager = KafkaTestManager()

    # Create test harness
    harness = PipelineTestHarness(service_manager, kafka_manager, auth_manager)

    try:
        # Phase 1: Setup batch with student matching
        batch_id, correlation_id = await harness.setup_regular_batch_with_student_matching(
            essay_files=essay_files
        )

        logger.info(f"✅ Batch {batch_id} ready for NLP pipeline execution")

        # Phase 2: Execute NLP pipeline
        nlp_result = await harness.execute_pipeline(
            pipeline_name="nlp",
            expected_steps=["spellcheck", "nlp"],
            expected_completion_event="batch.nlp.analysis.completed",
            validate_phase_pruning=False,  # First run, no pruning expected
        )

        # Validate results
        assert nlp_result.all_steps_completed, "NLP pipeline did not complete successfully"
        assert "spellcheck" in nlp_result.executed_steps, "Spellcheck phase not executed"
        assert "nlp" in nlp_result.executed_steps, "NLP analysis phase not executed"

        logger.info(
            f"✅ Complete NLP pipeline success! "
            f"Executed steps: {nlp_result.executed_steps} "
            f"in {nlp_result.execution_time_seconds:.2f}s"
        )

        # Log final event for debugging
        if nlp_result.completion_event:
            event_type = nlp_result.completion_event.get("event_type")
            logger.info(f"Final event type: {event_type}")

    finally:
        # Cleanup
        await harness.cleanup()
        reset_test_event_factory()


@pytest.mark.slow
@pytest.mark.e2e
@pytest.mark.functional
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_e2e_nlp_pipeline_guest_batch(
    clean_distributed_state: Any,
) -> None:
    """
    Test NLP pipeline for GUEST batches (no student matching).

    This test validates:
    1. Batch registration WITHOUT class_id (GUEST flow)
    2. File upload and content provisioning
    3. Direct transition to READY_FOR_PIPELINE_EXECUTION
    4. NLP pipeline execution (spellcheck + nlp analysis)

    Uses real essays but without student matching phase.
    """
    # Load real essays
    essay_dir = Path(
        "/Users/olofs_mba/Documents/Repos/huledu-reboot/test_uploads/Book-Report-ES24B-2025-04-09-104843"
    )
    essay_files = list(essay_dir.glob("*.docx"))[:5]  # Use fewer essays for guest test
    logger.info(f"📚 Using {len(essay_files)} essays for GUEST batch test")

    # Setup authentication
    auth_manager = AuthTestManager()
    guest_user = auth_manager.create_test_user(role="guest")

    # Initialize service manager
    service_manager = ServiceTestManager(auth_manager=auth_manager)

    # Verify services
    endpoints = await service_manager.get_validated_endpoints()
    assert len(endpoints) >= 4
    logger.info(f"✅ {len(endpoints)} services validated healthy")

    # Setup Kafka manager
    kafka_manager = KafkaTestManager()

    # Create test harness
    harness = PipelineTestHarness(service_manager, kafka_manager, auth_manager)

    try:
        # Setup GUEST batch (no student matching)
        batch_id, correlation_id = await harness.setup_guest_batch(
            essay_files=essay_files,
            user=guest_user,
        )

        logger.info(f"📝 GUEST batch {batch_id} ready for NLP pipeline execution")

        # Execute NLP pipeline directly (no student matching phase)
        nlp_result = await harness.execute_pipeline(
            pipeline_name="nlp",
            expected_steps=["spellcheck", "nlp"],
            expected_completion_event="batch.nlp.analysis.completed",
            validate_phase_pruning=False,
        )

        # Validate results
        assert nlp_result.all_steps_completed, "GUEST NLP pipeline did not complete successfully"
        assert "spellcheck" in nlp_result.executed_steps, "Spellcheck phase not executed"
        assert "nlp" in nlp_result.executed_steps, "NLP analysis phase not executed"

        logger.info(
            f"✅ GUEST batch NLP pipeline success! "
            f"Executed steps: {nlp_result.executed_steps} "
            f"in {nlp_result.execution_time_seconds:.2f}s"
        )

    finally:
        # Cleanup harness resources
        await harness.cleanup()
        reset_test_event_factory()
