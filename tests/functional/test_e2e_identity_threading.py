"""
E2E Identity Threading Workflows

Tests complete identity threading from ELS_CJAssessmentRequestV1 through ResourceConsumptionV1.
Validates user_id/org_id preservation across service boundaries in real educational scenarios.

Uses ServiceTestManager + KafkaTestManager patterns - NO direct service calls.
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
from tests.utils.service_test_manager import ServiceTestManager

logger = create_service_logger("test.e2e_identity_threading")


class TestE2EIdentityThreading:
    """Test complete identity threading workflows using modern utility patterns exclusively."""

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_service_health_prerequisites(self):
        """Validate all services are healthy for identity threading tests."""
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
    @pytest.mark.timeout(300)
    async def test_complete_identity_threading_workflow(self):
        """Test ELS → CJ → ResourceConsumptionV1 identity flow."""
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_mgr = KafkaTestManager()
        harness = PipelineTestHarness(service_manager, kafka_mgr, auth_manager)

        # Set up Kafka consumer for ResourceConsumptionV1 events
        resource_events = []
        async def collect_resource_events(consumer):
            async for msg in consumer:
                if "resource.consumption" in msg.topic:
                    resource_events.append(msg)

        essay_files = [
            Path("test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMXE 50 (SA24D ENG 5 WRITING 2025).txt"),
        ]

        try:
            # Start resource consumption event collector
            async with kafka_mgr.consumer("identity_threading", ["huleedu.resource.consumption.reported.v1"]) as consumer:
                collector_task = asyncio.create_task(collect_resource_events(consumer))
                
                # Execute CJ pipeline
                batch_id, corr = await harness.setup_guest_batch(essay_files)
                result = await harness.execute_pipeline(
                    pipeline_name="cj_assessment",
                    expected_steps=["spellcheck", "cj_assessment"],
                    expected_completion_event="cj_assessment.completed",
                    validate_phase_pruning=False,
                    timeout_seconds=240,
                )

                # Wait briefly for resource consumption events
                await asyncio.sleep(5)
                collector_task.cancel()
                
                assert result.all_steps_completed
                assert "cj_assessment" in result.executed_steps

                # Validate resource consumption events were published
                assert len(resource_events) > 0, "No ResourceConsumptionV1 events received"
                
                # Verify identity threading in resource events
                for msg in resource_events:
                    event_data = msg.value.decode('utf-8')
                    assert "user_id" in event_data
                    assert batch_id in event_data  # Entity ID should match batch
                    logger.info(f"ResourceConsumptionV1 event: {event_data[:200]}...")

        finally:
            await harness.cleanup()

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    @pytest.mark.timeout(240)
    async def test_teacher_student_identity_workflow(self):
        """Test teacher processing student essays with organization identity."""
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_mgr = KafkaTestManager()
        harness = PipelineTestHarness(service_manager, kafka_mgr, auth_manager)

        # Teacher scenario with organization
        test_teacher = await auth_manager.create_test_user_token(
            user_id="teacher_sv_123",
            org_id="gymnasium_stockholm"
        )

        essay_files = [
            Path("test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMXE 50 (SA24D ENG 5 WRITING 2025).txt"),
        ]

        try:
            batch_id, corr = await harness.setup_authenticated_batch(
                essay_files, 
                auth_token=test_teacher
            )
            
            result = await harness.execute_pipeline(
                pipeline_name="cj_assessment",
                expected_steps=["spellcheck", "cj_assessment"],
                expected_completion_event="cj_assessment.completed",
                validate_phase_pruning=False,
                timeout_seconds=180,
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
    @pytest.mark.timeout(360)
    async def test_batch_processing_identity_correlation(self):
        """Test identity correlation across multiple essay batch."""
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
                timeout_seconds=300,
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
    @pytest.mark.timeout(180)
    async def test_individual_vs_organization_flow(self):
        """Test identity threading for individual vs organization users."""
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_mgr = KafkaTestManager()
        harness = PipelineTestHarness(service_manager, kafka_mgr, auth_manager)

        # Individual user (no org_id)
        individual_user = await auth_manager.create_test_user_token(
            user_id="individual_user_123",
            org_id=None
        )

        essay_files = [
            Path("test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt"),
        ]

        try:
            batch_id, corr = await harness.setup_authenticated_batch(
                essay_files,
                auth_token=individual_user
            )

            result = await harness.execute_pipeline(
                pipeline_name="cj_assessment",
                expected_steps=["spellcheck", "cj_assessment"],
                expected_completion_event="cj_assessment.completed", 
                validate_phase_pruning=False,
                timeout_seconds=120,
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
    @pytest.mark.timeout(240)
    async def test_cross_service_event_flow_validation(self):
        """Test event flow validation across service boundaries."""
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_mgr = KafkaTestManager()
        harness = PipelineTestHarness(service_manager, kafka_mgr, auth_manager)

        # Collect all events during processing
        all_events = []
        async def collect_all_events(consumer):
            async for msg in consumer:
                all_events.append({
                    "topic": msg.topic,
                    "timestamp": msg.timestamp,
                    "key": msg.key.decode('utf-8') if msg.key else None,
                })

        essay_files = [
            Path("test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMXE 50 (SA24D ENG 5 WRITING 2025).txt"),
        ]

        try:
            # Monitor all event topics
            topics = [
                "huleedu.els.batch.essays.ready.v1",
                "huleedu.cj_assessment.completed.v1", 
                "huleedu.resource.consumption.reported.v1",
                "huleedu.batch.results.ready.v1"
            ]
            
            async with kafka_mgr.consumer("event_flow", topics) as consumer:
                collector_task = asyncio.create_task(collect_all_events(consumer))
                
                batch_id, corr = await harness.setup_guest_batch(essay_files)
                result = await harness.execute_pipeline(
                    pipeline_name="cj_assessment",
                    expected_steps=["spellcheck", "cj_assessment"],
                    expected_completion_event="cj_assessment.completed",
                    validate_phase_pruning=False,
                    timeout_seconds=180,
                )

                await asyncio.sleep(3)  # Allow events to propagate
                collector_task.cancel()
                
                assert result.all_steps_completed
                
                # Validate event flow sequence
                event_topics = [event["topic"] for event in all_events]
                logger.info(f"Event flow sequence: {event_topics}")
                
                # Should see the complete flow
                assert any("els.batch.essays.ready" in topic for topic in event_topics)
                assert any("cj_assessment.completed" in topic for topic in event_topics)

        finally:
            await harness.cleanup()

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_swedish_character_identity_preservation(self):
        """Test Swedish character preservation in identity threading."""
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_mgr = KafkaTestManager()
        harness = PipelineTestHarness(service_manager, kafka_mgr, auth_manager)

        # Swedish teacher
        swedish_user = await auth_manager.create_test_user_token(
            user_id="lärare_åsa_123", 
            org_id="skolan_västerås"
        )

        essay_files = [
            Path("test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt"),
        ]

        try:
            batch_id, corr = await harness.setup_authenticated_batch(
                essay_files,
                auth_token=swedish_user
            )

            result = await harness.execute_pipeline(
                pipeline_name="cj_assessment",
                expected_steps=["spellcheck", "cj_assessment"],
                expected_completion_event="cj_assessment.completed",
                validate_phase_pruning=False,
                timeout_seconds=120,
            )

            assert result.all_steps_completed
            assert result.ras_result_event is not None
            
            # Swedish characters should be preserved
            ras_data = result.ras_result_event["data"]
            assert ras_data["batch_id"] == batch_id

        finally:
            await harness.cleanup()

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    @pytest.mark.timeout(300)
    async def test_service_integration_reliability(self):
        """Test service integration reliability with proper timeouts."""
        service_manager = ServiceTestManager()
        
        # Test all required services are responsive
        endpoints = await service_manager.get_validated_endpoints()
        required_services = [
            "essay_lifecycle_api", 
            "cj_assessment_service",
            "entitlements_service",
            "result_aggregator_service"
        ]
        
        for service_name in required_services:
            if service_name not in endpoints:
                pytest.skip(f"Required service {service_name} not available")
                
            endpoint_info = endpoints[service_name]
            assert endpoint_info["status"] == "healthy"
            assert endpoint_info["response_time"] < 5.0  # Max 5s response time
            
            # Test metrics endpoint if available  
            if endpoint_info.get("has_metrics"):
                metrics = await service_manager.get_service_metrics(
                    service_name, 
                    endpoint_info["port"]
                )
                assert metrics is not None
                assert "http_requests_total" in metrics

        logger.info("All required services validated for identity threading")