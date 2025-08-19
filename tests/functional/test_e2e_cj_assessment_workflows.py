"""
E2E CJ Assessment Pipeline Workflows

Consolidated test suite for CJ Assessment pipeline validation, extracted and modernized from Step 5.
Tests complete CJ Assessment processing workflow from multiple essay uploads through ranking results

Uses modern utility patterns (ServiceTestManager + KafkaTestManager) throughout - NO direct calls.
Preserves all CJ assessment business logic:
real student essays, ranking validation, multi-essay coordination.
"""

from __future__ import annotations

import uuid
from datetime import UTC
from pathlib import Path
from typing import Any

import pytest
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)
from common_core.status_enums import ProcessingStage

from tests.functional.pipeline_test_harness import PipelineTestHarness
from tests.utils.auth_manager import AuthTestManager
from tests.utils.kafka_test_manager import KafkaTestManager, kafka_event_monitor
from tests.utils.service_test_manager import ServiceTestManager


class TestE2ECJAssessmentWorkflows:
    """Test CJ Assessment pipeline workflows using modern utility patterns exclusively."""

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_content_service_health_prerequisite(self):
        """Validate Content Service is healthy before CJ Assessment tests."""
        service_manager = ServiceTestManager()
        endpoints = await service_manager.get_validated_endpoints()

        if "content_service" not in endpoints:
            pytest.skip("Content Service not available for CJ Assessment testing")

        # Health validation is built into get_validated_endpoints()
        assert endpoints["content_service"]["status"] == "healthy"

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_cj_assessment_service_health_prerequisite(self):
        """Validate CJ Assessment Service metrics before pipeline tests."""
        service_manager = ServiceTestManager()

        # Use utility to get metrics instead of direct HTTP call
        metrics_text = await service_manager.get_service_metrics("cj_assessment_service", 9095)

        if metrics_text is None:
            pytest.skip("CJ Assessment Service metrics not available")

        # Validate Prometheus metrics format
        assert "http_requests_total" in metrics_text  # Basic Prometheus metric

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    @pytest.mark.timeout(300)  # 5 minute timeout for complete CJ pipeline
    async def test_complete_cj_assessment_processing_pipeline(self):
        """
        Test CJ pipeline end-to-end using the PipelineTestHarness (guest flow):
        1) Register batch and upload essays via File Service
        2) Publish client pipeline request for 'cj_assessment'
        3) Wait for CJ thin completion event (ELS)
        4) Validate rich AssessmentResult event (RAS)
        """
        # Managers and harness
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_mgr = KafkaTestManager()
        harness = PipelineTestHarness(service_manager, kafka_mgr, auth_manager)

        # Use real student essays (guest flow)
        essay_files = [
            Path("test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMXE 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMUX 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMUU 50 (SA24D ENG 5 WRITING 2025).txt"),
        ]

        completed_topic = topic_name(ProcessingEvent.BATCH_ASSESSMENT_COMPLETED)
        results_topic = topic_name(ProcessingEvent.BATCH_RESULTS_READY)

        try:
            # Setup guest batch and run CJ pipeline
            batch_id, corr = await harness.setup_guest_batch(essay_files)

            result = await harness.execute_pipeline(
                pipeline_name="cj_assessment",
                expected_steps=["spellcheck", "cj_assessment"],
                expected_completion_event="cj_assessment.completed",
                validate_phase_pruning=False,
                timeout_seconds=240,
            )

            assert result.all_steps_completed, "CJ pipeline did not complete"
            assert "cj_assessment" in result.executed_steps

            # Collect and validate rich RAS result
            async with kafka_event_monitor(
                "cj_assessment_pipeline_test_harness",
                [completed_topic, results_topic],
            ) as consumer:
                result_events = await kafka_mgr.collect_events(
                    consumer,
                    expected_count=1,
                    timeout_seconds=240,
                    event_filter=lambda event: (
                        event.get("event_type") == results_topic
                        and event.get("correlation_id") == str(corr)
                    ),
                )

                assert len(result_events) == 1, (
                    f"Expected 1 assessment result event, got {len(result_events)}"
                )

                assessment_result = result_events[0]["data"]["data"]
                essay_results = assessment_result.get("essay_results", [])
                student_results = [r for r in essay_results if not r.get("is_anchor")]

                assert len(student_results) >= len(essay_files)
                assert assessment_result["cj_assessment_job_id"] is not None

                for res in student_results:
                    assert "essay_id" in res
                    assert "normalized_score" in res
                    assert "letter_grade" in res
                    assert "bt_score" in res

        finally:
            await harness.cleanup()

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_cj_assessment_pipeline_minimal_essays(self):
        """
        Test CJ pipeline end-to-end with minimal essays using PipelineTestHarness (guest flow).
        Validates thin completion and rich results with exactly 2 student essays.
        """
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_mgr = KafkaTestManager()
        harness = PipelineTestHarness(service_manager, kafka_mgr, auth_manager)

        # Minimal set: 2 essays
        essay_files = [
            Path("test_uploads/real_test_batch/MHHXGLUU 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGLMX 50 (SA24D ENG 5 WRITING 2025).txt"),
        ]

        completed_topic = topic_name(ProcessingEvent.BATCH_ASSESSMENT_COMPLETED)
        results_topic = topic_name(ProcessingEvent.BATCH_RESULTS_READY)

        try:
            batch_id, corr = await harness.setup_guest_batch(essay_files)

            result = await harness.execute_pipeline(
                pipeline_name="cj_assessment",
                expected_steps=["spellcheck", "cj_assessment"],
                expected_completion_event="cj_assessment.completed",
                validate_phase_pruning=False,
                timeout_seconds=180,
            )

            assert result.all_steps_completed, "CJ pipeline did not complete"
            assert "cj_assessment" in result.executed_steps

            # Validate rich results contain exactly 2 student essays
            async with kafka_event_monitor(
                "minimal_cj_assessment_test_harness",
                [completed_topic, results_topic],
            ) as consumer:
                result_events = await kafka_mgr.collect_events(
                    consumer,
                    expected_count=1,
                    timeout_seconds=180,
                    event_filter=lambda event: (
                        event.get("event_type") == results_topic
                        and event.get("correlation_id") == str(corr)
                    ),
                )

                assert len(result_events) == 1
                assessment_result = result_events[0]["data"]["data"]
                essay_results = assessment_result.get("essay_results", [])
                student_results = [r for r in essay_results if not r.get("is_anchor")]

                assert len(student_results) == 2
        finally:
            await harness.cleanup()

    def _create_cj_assessment_request_event(
        self,
        batch_id: str,
        essay_storage_refs: list[dict[str, str]],
        correlation_id: str,
        language: str = "en",
        course_code: CourseCode = CourseCode.ENG5,
        essay_instructions: str = "Write an essay.",
    ) -> dict[str, Any]:
        """
        Create ELS_CJAssessmentRequestV1 event structure.

        Helper method that creates the proper EventEnvelope structure for CJ assessment requests.
        """
        from datetime import datetime

        # Create the essay input references
        essay_inputs = []
        for ref in essay_storage_refs:
            essay_input = EssayProcessingInputRefV1(
                essay_id=ref["essay_id"],
                text_storage_id=ref["storage_id"],
            )
            essay_inputs.append(essay_input)

        # Create SystemProcessingMetadata (match original working implementation)
        system_metadata = SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            timestamp=datetime.now(UTC),
            processing_stage=ProcessingStage.INITIALIZED,
            event=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED.value,
        )

        # Create the request data
        cj_request_data = ELS_CJAssessmentRequestV1(
            entity_id=batch_id,
            entity_type="batch",
            system_metadata=system_metadata,
            essays_for_cj=essay_inputs,
            language=language,
            course_code=course_code,
            essay_instructions=essay_instructions,
            llm_config_overrides=None,  # Use service defaults
        )

        # Create EventEnvelope
        event_envelope: EventEnvelope[ELS_CJAssessmentRequestV1] = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type=topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED),
            event_timestamp=datetime.now(UTC),
            source_service="test_cj_assessment_workflows",
            correlation_id=uuid.UUID(correlation_id),
            data=cj_request_data,
        )

        # Convert to dict for Kafka publishing, serializing UUIDs to strings
        return event_envelope.model_dump(mode="json")
