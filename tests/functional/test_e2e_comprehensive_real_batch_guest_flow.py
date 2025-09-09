"""
Comprehensive End-to-End Real Batch Test

This test validates the complete pipeline using real student essays from
/test_uploads/real_test_batch/ and follows the ACTUAL orchestration flow:

1. File Upload → EssayContentProvisionedV1 events
2. ELS aggregates → BatchEssaysReady event
3. BOS receives BatchEssaysReady → publishes BatchServiceSpellcheckInitiateCommandDataV1
4. Spellcheck Service processes → publishes SpellCheckCompletedV1
5. BOS receives phase completion → publishes BatchServiceCJAssessmentInitiateCommandDataV1
6. CJ Assessment Service processes → publishes CJAssessmentCompletedV1

Tests both phases with real orchestration and real student essays.
"""

import pytest

from tests.functional.comprehensive_pipeline_utils import load_real_test_essays
from tests.functional.pipeline_test_harness import PipelineTestHarness
from tests.utils.auth_manager import AuthTestManager
from tests.utils.distributed_state_manager import distributed_state_manager
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager


@pytest.mark.slow
@pytest.mark.e2e
@pytest.mark.functional
@pytest.mark.asyncio
@pytest.mark.timeout(240)  # 4 minute timeout for complete pipeline with mock LLM
async def test_comprehensive_real_batch_pipeline():
    """
    Test complete pipeline with real student essays through actual BOS orchestration.

    This test validates:
    1. File upload and content provisioning
    2. BOS orchestration triggering spellcheck phase
    3. Spellcheck completion and phase transition
    4. BOS orchestration triggering CJ assessment phase
    5. CJ assessment completion and final results

    Uses real student essays and follows actual event orchestration.
    Uses mock LLM for fast, cost-effective testing.
    Now using PipelineTestHarness for proper credit provisioning.
    """
    # Ensure clean distributed state for test isolation
    await distributed_state_manager.quick_redis_cleanup()

    # Validate real test essays are available
    test_essays = await load_real_test_essays(max_essays=25)

    # Initialize managers
    auth_manager = AuthTestManager()
    service_manager = ServiceTestManager(auth_manager=auth_manager)
    kafka_manager = KafkaTestManager()

    # Create test teacher for the batch
    test_teacher = auth_manager.create_teacher_user("Comprehensive Test Teacher")

    # Validate all services are healthy
    endpoints = await service_manager.get_validated_endpoints()
    assert len(endpoints) >= 4, f"Expected at least 4 services, got {len(endpoints)}"
    print(f"✅ {len(endpoints)} services validated healthy")

    # Initialize PipelineTestHarness with proper credit provisioning
    harness = PipelineTestHarness(service_manager, kafka_manager, auth_manager)

    try:
        # Setup guest batch with credit provisioning (harness does this automatically)
        print("📝 Setting up GUEST batch with credit provisioning...")
        batch_id, correlation_id = await harness.setup_guest_batch(
            essay_files=test_essays, user=test_teacher
        )
        print(f"✅ Batch {batch_id} created with credits provisioned")
        print(f"🔗 Batch correlation ID: {correlation_id}")

        # Execute the pipeline using harness (which triggers via API Gateway)
        print("🚀 Executing cj_assessment pipeline...")
        result = await harness.execute_pipeline(
            pipeline_name="cj_assessment",
            expected_steps=["spellcheck", "cj_assessment"],
            expected_completion_event="cj_assessment.completed",
            validate_phase_pruning=False,
            timeout_seconds=120,  # Increased timeout for 25 essays
        )

        # Validate pipeline completed successfully
        assert result.all_steps_completed, "Pipeline did not complete all steps"
        assert "spellcheck" in result.executed_steps, "Spellcheck phase not executed"
        assert "cj_assessment" in result.executed_steps, "CJ assessment phase not executed"

        # Check that we got RAS results
        assert result.ras_result_event is not None, "No RAS result event received"
        ras_data = result.ras_result_event["data"]
        assert ras_data["batch_id"] == batch_id, "RAS result batch_id mismatch"
        assert ras_data["total_essays"] == len(test_essays), "Essay count mismatch"

        print(f"✅ Complete pipeline success! All {len(test_essays)} essays processed")
        print(f"   Execution time: {result.execution_time_seconds:.2f}s")
        print(f"   Phases executed: {result.executed_steps}")
        print(f"   Overall status: {ras_data.get('overall_status')}")

    finally:
        # Cleanup harness resources
        await harness.cleanup()
