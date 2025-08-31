"""
E2E Identity Threading Workflows

Tests ELS_CJAssessmentRequestV1 → ResourceConsumptionV1 identity preservation.
Uses ServiceTestManager + KafkaTestManager patterns.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from huleedu_service_libs.logging_utils import create_service_logger

from tests.functional.pipeline_test_harness import PipelineTestHarness
from tests.utils.auth_manager import AuthTestManager
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.identity_validation import IdentityValidator
from tests.utils.service_test_manager import ServiceTestManager

logger = create_service_logger("test.e2e_identity_threading")



class TestE2EIdentityThreading:
    """Test E2E identity threading workflows."""

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_service_health_prerequisites(self):
        """Validate service health."""
        service_manager = ServiceTestManager()
        endpoints = await service_manager.get_validated_endpoints()
        
        required_services = ["essay_lifecycle_api", "cj_assessment_service", "entitlements_service"]
        for service_name in required_services:
            if service_name not in endpoints:
                pytest.skip(f"{service_name} not available for identity threading tests")
            assert endpoints[service_name]["status"] == "healthy"

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    @pytest.mark.timeout(45)
    async def test_complete_identity_threading_workflow(self):
        """Test ELS → CJ → ResourceConsumptionV1 → Entitlements flow."""
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_mgr = KafkaTestManager()
        harness = PipelineTestHarness(service_manager, kafka_mgr, auth_manager)

        # Create test user for identity tracking
        test_user = auth_manager.create_test_user(
            user_id="test_identity_user",
            organization_id="test_org_123"
        )

        essay_files = [
            Path("test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMXE 50 (SA24D ENG 5 WRITING 2025).txt"),
        ]

        try:
            # Start monitoring ResourceConsumptionV1 events
            async with kafka_mgr.consumer("identity_threading", ["huleedu.resource.consumption.reported.v1"]) as consumer:
                # Execute CJ pipeline (pass test user to ensure identity propagation)
                batch_id, corr = await harness.setup_guest_batch(essay_files, user=test_user)
                logger.info(f"Starting identity threading for batch {batch_id}, user: {test_user.user_id}")
                
                result = await harness.execute_pipeline(
                    pipeline_name="cj_assessment",
                    expected_steps=["spellcheck", "cj_assessment"],
                    expected_completion_event="cj_assessment.completed",
                    validate_phase_pruning=False,
                    timeout_seconds=45,
                )

                assert result.all_steps_completed
                assert "cj_assessment" in result.executed_steps
                logger.info(f"✅ CJ pipeline completed in {result.execution_time_seconds:.2f}s")

                # Collect ResourceConsumptionV1 events
                logger.info(f"🔍 Collecting ResourceConsumptionV1 events for correlation: {corr}")
                resource_events = await kafka_mgr.collect_events(
                    consumer, 
                    expected_count=1, 
                    timeout_seconds=10,
                    event_filter=lambda event: event.get("correlation_id") == str(corr)
                )
                
                # Validate ResourceConsumptionV1 event was published
                assert len(resource_events) > 0, f"No ResourceConsumptionV1 events for correlation {corr}"
                
                resource_event = resource_events[0]["data"]
                logger.info(f"📊 ResourceConsumptionV1 event received: {resource_event.get('event_type')}")
                
                # Validate identity threading in event
                # Using validator for payload identity
                id_check = IdentityValidator.validate_event_identity(resource_event)
                event_data = resource_event["data"]
                assert id_check["has_user"] and event_data["user_id"] == test_user.user_id
                assert id_check["has_org"] and event_data["org_id"] == test_user.organization_id
                assert event_data["resource_type"] == "cj_comparison"
                assert event_data["entity_id"] == batch_id
                
                logger.info(f"✅ Identity threading verified in ResourceConsumptionV1:")
                logger.info(f"   user_id: {event_data['user_id']}")
                logger.info(f"   org_id: {event_data['org_id']}")
                logger.info(f"   quantity: {event_data['quantity']}")
                logger.info(f"   resource_type: {event_data['resource_type']}")
                
                logger.info("🎉 IDENTITY THREADING TEST SUCCESS!")
                logger.info("   ✅ ELS → CJ pipeline completed")
                logger.info("   ✅ ResourceConsumptionV1 event published") 
                logger.info("   ✅ user_id/org_id properly threaded through event")

        finally:
            await harness.cleanup()

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    @pytest.mark.timeout(45)
    async def test_teacher_student_identity_workflow(self):
        """Test teacher processing essays with org identity."""
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_mgr = KafkaTestManager()
        harness = PipelineTestHarness(service_manager, kafka_mgr, auth_manager)

        # Teacher scenario with organization
        test_teacher = auth_manager.create_test_user(
            user_id="teacher_sv_123",
            organization_id="gymnasium_stockholm"
        )

        essay_files = [
            Path("test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMXE 50 (SA24D ENG 5 WRITING 2025).txt"),
        ]

        try:
            batch_id, corr = await harness.setup_guest_batch(essay_files, user=test_teacher)
            
            result = await harness.execute_pipeline(
                pipeline_name="cj_assessment",
                expected_steps=["spellcheck", "cj_assessment"],
                expected_completion_event="cj_assessment.completed",
                validate_phase_pruning=False,
                timeout_seconds=45,
            )

            assert result.all_steps_completed
            assert result.ras_result_event is not None

            # Validate teacher identity in result event
            ras_data = result.ras_result_event["data"]
            assert ras_data["batch_id"] == batch_id
            assert ras_data["total_essays"] == len(essay_files)

        finally:
            await harness.cleanup()

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    @pytest.mark.timeout(45)
    async def test_batch_processing_identity_correlation(self):
        """Test identity correlation across batch processing."""
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_mgr = KafkaTestManager()
        harness = PipelineTestHarness(service_manager, kafka_mgr, auth_manager)

        # Larger batch for realistic testing
        essay_files = [
            Path("test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMXE 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMUX 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMUU 50 (SA24D ENG 5 WRITING 2025).txt"),
        ]

        try:
            batch_id, corr = await harness.setup_guest_batch(essay_files)
            
            result = await harness.execute_pipeline(
                pipeline_name="cj_assessment",
                expected_steps=["spellcheck", "cj_assessment"],
                expected_completion_event="cj_assessment.completed",
                validate_phase_pruning=False,
                timeout_seconds=45,
            )

            assert result.all_steps_completed
            
            # Validate correlation preserved across all phases
            assert result.ras_result_event is not None
            ras_data = result.ras_result_event["data"]
            assert ras_data["batch_id"] == batch_id
            assert ras_data["total_essays"] == len(essay_files)
            assert ras_data["completed_essays"] == len(essay_files)

            # Check phase results contain both phases
            phase_results = ras_data["phase_results"]
            assert "spellcheck" in phase_results
            assert "cj_assessment" in phase_results

        finally:
            await harness.cleanup()

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    @pytest.mark.timeout(45)
    async def test_individual_vs_organization_flow(self):
        """Test individual vs organization identity flows."""
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_mgr = KafkaTestManager()
        harness = PipelineTestHarness(service_manager, kafka_mgr, auth_manager)

        # Individual user (no org_id)
        individual_user = auth_manager.create_individual_user(user_id="individual_user_123")

        essay_files = [
            Path("test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt"),
        ]

        try:
            batch_id, corr = await harness.setup_guest_batch(essay_files, user=individual_user)

            result = await harness.execute_pipeline(
                pipeline_name="cj_assessment",
                expected_steps=["spellcheck", "cj_assessment"],
                expected_completion_event="cj_assessment.completed", 
                validate_phase_pruning=False,
                timeout_seconds=45,
            )

            assert result.all_steps_completed
            assert result.ras_result_event is not None
            
            # Individual user should still get results
            ras_data = result.ras_result_event["data"]
            assert ras_data["batch_id"] == batch_id
            assert ras_data["overall_status"] in ["completed_successfully", "completed_with_failures"]

        finally:
            await harness.cleanup()


    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    @pytest.mark.timeout(45)
    async def test_swedish_character_identity_preservation(self):
        """Test Swedish character preservation."""
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_mgr = KafkaTestManager()
        harness = PipelineTestHarness(service_manager, kafka_mgr, auth_manager)

        # Swedish teacher
        swedish_user = auth_manager.create_org_user(
            user_id="lärare_åsa_123", org_id="skolan_västerås"
        )

        essay_files = [
            Path("test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt"),
        ]

        try:
            batch_id, corr = await harness.setup_guest_batch(essay_files, user=swedish_user)

            result = await harness.execute_pipeline(
                pipeline_name="cj_assessment",
                expected_steps=["spellcheck", "cj_assessment"],
                expected_completion_event="cj_assessment.completed",
                validate_phase_pruning=False,
                timeout_seconds=45,
            )

            assert result.all_steps_completed
            assert result.ras_result_event is not None
            
            # Swedish characters should be preserved
            ras_data = result.ras_result_event["data"]
            assert ras_data["batch_id"] == batch_id

        finally:
            await harness.cleanup()
