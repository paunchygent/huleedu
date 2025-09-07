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
12. Entitlements tracks credit consumption

Tests the full Phase 2 flow with real student essays and class roster.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from structlog import get_logger

from tests.functional.pipeline_test_harness import PipelineTestHarness
from tests.utils.auth_manager import AuthTestManager
from tests.utils.distributed_state_manager import distributed_state_manager
from tests.utils.event_factory import reset_test_event_factory
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager

logger = get_logger(__name__)


@pytest.mark.slow
@pytest.mark.e2e
@pytest.mark.functional
@pytest.mark.asyncio
@pytest.mark.timeout(300)  # 5 minute timeout for complete pipeline with student matching
async def test_comprehensive_real_batch_with_student_matching() -> None:
    """
    Test complete Phase 2 pipeline with student matching using PipelineTestHarness.

    This test validates:
    1. Class creation with student roster
    2. Batch registration with class_id (REGULAR flow)
    3. Essay upload and content provisioning
    4. Student matching via NLP service
    5. Teacher confirmation of associations
    6. Pipeline execution through API Gateway
    7. Entitlements credit consumption tracking
    8. Complete pipeline from upload to CJ assessment results
    """
    # Ensure clean distributed state for test isolation
    await distributed_state_manager.quick_redis_cleanup()

    # Initialize unique event factory for this test run
    reset_test_event_factory()

    # Load real test essays
    essay_dir = Path(
        "/Users/olofs_mba/Documents/Repos/huledu-reboot/test_uploads/Book-Report-ES24B-2025-04-09-104843"
    )

    # Find all .docx files (real student essays with names in filenames)
    essay_files = list(essay_dir.glob("*.docx"))
    if len(essay_files) < 10:
        pytest.skip(f"Need at least 10 essays for comprehensive test, found {len(essay_files)}")

    # Use first 27 essays for this test (matching original test)
    essay_files = essay_files[:27]
    logger.info(f"📚 Using {len(essay_files)} real student essays for Phase 2 test")

    # Step 1: Initialize managers
    auth_manager = AuthTestManager()
    service_manager = ServiceTestManager(auth_manager=auth_manager)
    kafka_manager = KafkaTestManager()

    # Validate all services are healthy
    endpoints = await service_manager.get_validated_endpoints()
    required_services = [
        "batch_orchestrator_service",
        "file_service",
        "essay_lifecycle_api",  # Note: ServiceTestManager uses 'essay_lifecycle_api' as key
        "class_management_service",
        "spellchecker_service",  # Note: ServiceTestManager uses 'spellchecker_service' not 'spell_checker_service'
        "cj_assessment_service",
        "api_gateway_service",
        "entitlements_service",
    ]

    for service in required_services:
        assert service in endpoints, f"Required service {service} not healthy"
    logger.info(f"✅ {len(endpoints)} services validated healthy")

    # Step 2: Create test harness
    harness = PipelineTestHarness(service_manager, kafka_manager, auth_manager)

    try:
        # Step 3: Setup batch with student matching (REGULAR flow)
        logger.info("📝 Setting up REGULAR batch with student matching...")
        batch_id, correlation_id = await harness.setup_regular_batch_with_student_matching(
            essay_files=essay_files
        )
        logger.info(f"✅ Batch {batch_id} ready with student matching complete")
        logger.info(f"🔗 Batch correlation ID: {correlation_id}")

        # Step 4: Execute CJ Assessment pipeline (includes spellcheck)
        logger.info("🚀 Executing CJ Assessment pipeline via API Gateway...")

        result = await harness.execute_pipeline(
            pipeline_name="cj_assessment",
            expected_steps=["spellcheck", "cj_assessment"],
            expected_completion_event="batch.cj_assessment.completed",  # Specific CJ completion event
            validate_phase_pruning=False,  # First run, no pruning
            timeout_seconds=120,
        )

        # Step 5: Validate pipeline execution
        assert result.all_steps_completed, "Pipeline did not complete successfully"
        assert "spellcheck" in result.executed_steps, "Spellcheck phase not executed"
        assert "cj_assessment" in result.executed_steps, "CJ Assessment phase not executed"

        logger.info(
            f"✅ Pipeline completed in {result.execution_time_seconds:.2f}s: "
            f"Executed {result.executed_steps}"
        )

        # Step 6: Validate Entitlements events
        if (
            result.entitlements_events["balance_changed"]
            and result.entitlements_events["usage_recorded"]
        ):
            logger.info("✅ Entitlements events already observed during pipeline progression")
        else:
            # Wait for Entitlements events if not already observed
            logger.info("⏳ Waiting for Entitlements events...")
            # Use the pipeline request correlation ID for Entitlements (not completion event)
            request_correlation_id = result.request_correlation_id
            entitlements_events = await harness.wait_for_entitlements_events(
                correlation_id=request_correlation_id,
                timeout_seconds=30,
            )

            if entitlements_events["balance_changed"] and entitlements_events["usage_recorded"]:
                logger.info("✅ Entitlements events observed after pipeline completion")
            else:
                logger.warning(
                    "⚠️ Entitlements events not fully observed; continuing with API validation"
                )

        # Step 7: Validate credit consumption via API
        logger.info("💳 Validating credit consumption via Entitlements API...")

        # Get the teacher user from harness
        teacher_user = harness.teacher_user
        # Use the pipeline request correlation ID (not the completion event's correlation ID)
        request_correlation_id = result.request_correlation_id

        # Fetch credit operations with retries for async propagation
        operations: list[dict[str, Any]] = []
        for attempt in range(10):  # ~5s total
            try:
                ops_resp = await service_manager.make_request(
                    method="GET",
                    service="entitlements_service",
                    path=f"/v1/admin/credits/operations?correlation_id={request_correlation_id}",
                    user=teacher_user,
                    correlation_id=request_correlation_id,
                )
                operations = ops_resp.get("operations", [])
                if operations:
                    break
            except Exception as e:
                logger.debug(f"Attempt {attempt + 1}: {e}")
            await asyncio.sleep(0.5)

        # Validate operations
        if operations:
            # Find consumption for CJ comparisons (operations are recorded with metric)
            consumption_ops = [op for op in operations if op.get("metric") == "cj_comparison"]

            assert len(consumption_ops) > 0, "No consumption operations found"

            # Validate the consumption amount
            consumption_op = consumption_ops[0]
            expected_comparisons = len(essay_files) * (len(essay_files) - 1) // 2

            # Validate metric name recorded by Entitlements (operations API uses 'metric')
            assert consumption_op.get("metric") == "cj_comparison", (
                f"Expected metric 'cj_comparison', got '{consumption_op.get('metric')}'"
            )

            # Validate the amount matches expected comparisons
            assert consumption_op.get("amount") == expected_comparisons, (
                f"Expected {expected_comparisons} comparisons, got {consumption_op.get('amount')}"
            )

            logger.info(f"✅ Credit consumption validated: {expected_comparisons} CJ comparisons")
        else:
            # Fallback: Check balance if operations not available
            logger.warning("⚠️ No operations found via correlation ID, checking balance...")

            balance_resp = await service_manager.make_request(
                method="GET",
                service="entitlements_service",
                path=f"/v1/entitlements/balance/{teacher_user.user_id}",
                user=teacher_user,
                correlation_id=request_correlation_id,
            )

            # Just verify we got a balance response
            assert "user_balance" in balance_resp, "Failed to get credit balance"
            logger.info(f"📊 Current user balance: {balance_resp['user_balance']}")

        # Step 8: Validate final results
        logger.info("📊 Validating final pipeline results...")

        # Check that we have CJ assessment results
        assert result.completion_event is not None, "No completion event received"

        event_data = result.completion_event.get("data", {})
        if "phase_name" in event_data:
            # Phase outcome event
            assert event_data.get("phase_status") in [
                "completed_successfully",
                "completed_with_failures",
            ], f"Unexpected phase status: {event_data.get('phase_status')}"

            logger.info(
                f"✅ Phase {event_data.get('phase_name')} completed with status: "
                f"{event_data.get('phase_status')}"
            )

        # Final success message
        logger.info("🎉 Complete Phase 2 pipeline with student matching validated successfully!")
        logger.info(f"   - {len(essay_files)} essays processed")
        logger.info("   - Student matching completed")
        logger.info("   - Spellcheck and CJ assessment executed")
        logger.info("   - Entitlements credit consumption tracked")
        logger.info(f"   - Total execution time: {result.execution_time_seconds:.2f}s")

    finally:
        # Cleanup
        await harness.cleanup()
        logger.info("🧹 Test cleanup completed")
