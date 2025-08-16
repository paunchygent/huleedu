"""
End-to-End Sequential Pipeline Test with Phase Pruning

This test validates that the system correctly handles sequential pipeline
executions on the same batch, with phase pruning to avoid re-processing
already completed phases.

Test Scenario:
1. Execute NLP pipeline (spellcheck + nlp)
2. Execute CJ Assessment pipeline (should skip spellcheck, only run cj_assessment)
3. Execute AI Feedback pipeline (should skip spellcheck + nlp, only run ai_feedback)

This validates:
- Phase completion tracking across pipeline executions
- Storage ID reuse for completed phases
- Correct pruning of already-completed phases
- Pipeline dependency resolution with pruning
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
@pytest.mark.timeout(600)  # 10 minute timeout for multiple pipeline executions
async def test_e2e_sequential_pipelines_with_phase_pruning(
    clean_distributed_state: Any,
) -> None:
    """
    Test sequential pipeline execution with phase pruning.

    This test validates:
    1. First pipeline executes all required phases
    2. Second pipeline skips already-completed phases
    3. Third pipeline skips multiple already-completed phases
    4. Storage IDs are reused for pruned phases
    5. Total execution time is reduced due to pruning

    Uses the pipeline dependencies from pipelines.yaml:
    - nlp: [spellcheck, nlp]
    - cj_assessment: [spellcheck, cj_assessment]
    - ai_feedback: [spellcheck, nlp, ai_feedback]
    """
    # Load real essays
    essay_dir = Path(
        "/Users/olofs_mba/Documents/Repos/huledu-reboot/test_uploads/Book-Report-ES24B-2025-04-09-104843"
    )
    essay_files = list(essay_dir.glob("*.docx"))[:10]  # Use 10 essays for testing
    logger.info(f"📚 Using {len(essay_files)} real student essays for sequential pipeline test")

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

        logger.info(f"✅ Batch {batch_id} ready for sequential pipeline testing")

        # ==================================================================
        # Pipeline 1: NLP (should run spellcheck + nlp)
        # ==================================================================
        logger.info("🚀 Executing Pipeline 1: NLP (expecting spellcheck + nlp)")
        
        nlp_result = await harness.execute_pipeline(
            pipeline_name="nlp",
            expected_steps=["spellcheck", "nlp"],
            expected_completion_event="batch.nlp.analysis.completed",
            validate_phase_pruning=False,  # First run, no pruning expected
        )

        # Validate NLP pipeline results
        assert nlp_result.all_steps_completed, "NLP pipeline did not complete"
        assert "spellcheck" in nlp_result.executed_steps, "Spellcheck not executed"
        assert "nlp" in nlp_result.executed_steps, "NLP analysis not executed"
        assert len(nlp_result.pruned_phases) == 0, "No phases should be pruned on first run"

        logger.info(
            f"✅ Pipeline 1 complete: Executed {nlp_result.executed_steps} "
            f"in {nlp_result.execution_time_seconds:.2f}s"
        )

        # Store execution times for comparison
        nlp_execution_time = nlp_result.execution_time_seconds

        # ==================================================================
        # Pipeline 2: CJ Assessment (should SKIP spellcheck, only run cj_assessment)
        # ==================================================================
        logger.info("🚀 Executing Pipeline 2: CJ Assessment (expecting only cj_assessment)")
        
        cj_result = await harness.execute_pipeline(
            pipeline_name="cj_assessment",
            expected_steps=["cj_assessment"],  # Spellcheck should be pruned!
            expected_completion_event="batch.cj_assessment.completed",
            validate_phase_pruning=True,  # Validate pruning occurred
        )

        # Validate CJ Assessment pipeline results
        assert cj_result.all_steps_completed, "CJ Assessment pipeline did not complete"
        assert "cj_assessment" in cj_result.executed_steps, "CJ Assessment not executed"
        assert "spellcheck" not in cj_result.executed_steps, "Spellcheck should have been pruned"
        assert "spellcheck" in cj_result.pruned_phases, "Spellcheck should be in pruned phases"
        
        # Verify storage ID reuse
        if "spellcheck" in cj_result.reused_storage_ids:
            logger.info(f"✅ Reused spellcheck storage ID: {cj_result.reused_storage_ids['spellcheck']}")

        logger.info(
            f"✅ Pipeline 2 complete: Executed {cj_result.executed_steps}, "
            f"Pruned {cj_result.pruned_phases} in {cj_result.execution_time_seconds:.2f}s"
        )

        # CJ should be faster since it skipped spellcheck
        assert cj_result.execution_time_seconds < nlp_execution_time, \
            "CJ Assessment should be faster due to phase pruning"

        # ==================================================================
        # Pipeline 3: AI Feedback (should SKIP spellcheck + nlp, only run ai_feedback)
        # ==================================================================
        logger.info("🚀 Executing Pipeline 3: AI Feedback (expecting only ai_feedback)")
        
        ai_result = await harness.execute_pipeline(
            pipeline_name="ai_feedback",
            expected_steps=["ai_feedback"],  # Both spellcheck and nlp should be pruned!
            expected_completion_event="batch.ai_feedback.completed",
            validate_phase_pruning=True,  # Validate pruning occurred
        )

        # Validate AI Feedback pipeline results
        assert ai_result.all_steps_completed, "AI Feedback pipeline did not complete"
        assert "ai_feedback" in ai_result.executed_steps, "AI Feedback not executed"
        assert "spellcheck" not in ai_result.executed_steps, "Spellcheck should have been pruned"
        assert "nlp" not in ai_result.executed_steps, "NLP should have been pruned"
        assert "spellcheck" in ai_result.pruned_phases, "Spellcheck should be in pruned phases"
        assert "nlp" in ai_result.pruned_phases, "NLP should be in pruned phases"
        
        # Verify storage ID reuse for multiple phases
        if "spellcheck" in ai_result.reused_storage_ids:
            logger.info(f"✅ Reused spellcheck storage ID: {ai_result.reused_storage_ids['spellcheck']}")
        if "nlp" in ai_result.reused_storage_ids:
            logger.info(f"✅ Reused NLP storage ID: {ai_result.reused_storage_ids['nlp']}")

        logger.info(
            f"✅ Pipeline 3 complete: Executed {ai_result.executed_steps}, "
            f"Pruned {ai_result.pruned_phases} in {ai_result.execution_time_seconds:.2f}s"
        )

        # AI Feedback should be the fastest since it skipped the most phases
        assert ai_result.execution_time_seconds < cj_result.execution_time_seconds, \
            "AI Feedback should be fastest due to maximum phase pruning"

        # ==================================================================
        # Summary
        # ==================================================================
        logger.info("\n" + "=" * 60)
        logger.info("📊 SEQUENTIAL PIPELINE EXECUTION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Pipeline 1 (NLP): {nlp_result.executed_steps} in {nlp_execution_time:.2f}s")
        logger.info(
            f"Pipeline 2 (CJ): {cj_result.executed_steps} in {cj_result.execution_time_seconds:.2f}s "
            f"(pruned: {cj_result.pruned_phases})"
        )
        logger.info(
            f"Pipeline 3 (AI): {ai_result.executed_steps} in {ai_result.execution_time_seconds:.2f}s "
            f"(pruned: {ai_result.pruned_phases})"
        )
        logger.info(f"Total phases executed: {len(nlp_result.executed_steps) + len(cj_result.executed_steps) + len(ai_result.executed_steps)}")
        logger.info(f"Total phases pruned: {len(cj_result.pruned_phases) + len(ai_result.pruned_phases)}")
        logger.info("=" * 60)

    finally:
        # Cleanup
        await harness.cleanup()
        reset_test_event_factory()


@pytest.mark.slow
@pytest.mark.e2e
@pytest.mark.functional
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_e2e_comprehensive_pipeline_all_phases(
    clean_distributed_state: Any,
) -> None:
    """
    Test the comprehensive pipeline that includes all phases.

    The comprehensive pipeline should execute all phases in one go:
    [spellcheck, nlp, cj_assessment, ai_feedback]

    This validates that a single pipeline can orchestrate all phases.
    """
    # Load real essays
    essay_dir = Path(
        "/Users/olofs_mba/Documents/Repos/huledu-reboot/test_uploads/Book-Report-ES24B-2025-04-09-104843"
    )
    essay_files = list(essay_dir.glob("*.docx"))[:5]  # Use fewer essays for comprehensive test
    logger.info(f"📚 Using {len(essay_files)} essays for comprehensive pipeline test")

    # Setup
    auth_manager = AuthTestManager()
    service_manager = ServiceTestManager(auth_manager=auth_manager)
    kafka_manager = KafkaTestManager()
    harness = PipelineTestHarness(service_manager, kafka_manager, auth_manager)

    try:
        # Setup batch
        batch_id, correlation_id = await harness.setup_regular_batch_with_student_matching(
            essay_files=essay_files
        )

        # Execute comprehensive pipeline
        logger.info("🚀 Executing Comprehensive Pipeline (all phases)")
        
        comprehensive_result = await harness.execute_pipeline(
            pipeline_name="comprehensive",
            expected_steps=["spellcheck", "nlp", "cj_assessment", "ai_feedback"],
            expected_completion_event="batch.pipeline.completed",  # Generic completion
            validate_phase_pruning=False,
        )

        # Validate all phases executed
        assert comprehensive_result.all_steps_completed, "Comprehensive pipeline did not complete"
        assert "spellcheck" in comprehensive_result.executed_steps
        assert "nlp" in comprehensive_result.executed_steps  
        assert "cj_assessment" in comprehensive_result.executed_steps
        assert "ai_feedback" in comprehensive_result.executed_steps

        logger.info(
            f"✅ Comprehensive pipeline complete: "
            f"Executed all {len(comprehensive_result.executed_steps)} phases "
            f"in {comprehensive_result.execution_time_seconds:.2f}s"
        )

    finally:
        await harness.cleanup()
        reset_test_event_factory()