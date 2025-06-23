"""
E2E CJ Assessment Pipeline Workflows

Consolidated test suite for CJ Assessment pipeline validation, extracted and modernized from Step 5.
Tests complete CJ Assessment processing workflow from multiple essay uploads through ranking results

Uses modern utility patterns (ServiceTestManager + KafkaTestManager) throughout - NO direct calls.
Preserves all CJ assessment business logic:
real student essays, ranking validation, multi-essay coordination.
"""

import uuid
from datetime import UTC
from typing import Any

import pytest

from common_core.enums import BatchStatus, ProcessingEvent, ProcessingStage, topic_name
from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import (
    EntityReference,
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)
from tests.utils.kafka_test_manager import kafka_event_monitor, kafka_manager
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
        Test complete CJ Assessment pipeline: Content upload → Kafka event → Processing → Results

        Uses ServiceTestManager for Content Service interaction and KafkaTestManager for events.
        Validates the full business workflow:
        1. Upload multiple real student essays to Content Service (via utility)
        2. Simulate ELS_CJAssessmentRequestV1 event (via utility)
        3. Monitor for CJAssessmentCompletedV1 response (via utility)
        4. Validate CJ rankings and scores stored in Content Service (via utility)
        """
        service_manager = ServiceTestManager()
        correlation_id = str(uuid.uuid4())
        batch_id = str(uuid.uuid4())  # Use standard UUID format (36 chars) to match database schema

        # Use real student essays for CJ Assessment
        essay_files = [
            "test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt",
            "test_uploads/real_test_batch/MHHXGMXE 50 (SA24D ENG 5 WRITING 2025).txt",
            "test_uploads/real_test_batch/MHHXGMUX 50 (SA24D ENG 5 WRITING 2025).txt",
            "test_uploads/real_test_batch/MHHXGMUU 50 (SA24D ENG 5 WRITING 2025).txt",
        ]

        # Step 1: Upload essays to Content Service using utility
        print(f"📚 Uploading {len(essay_files)} real student essays")
        essay_storage_refs = []

        for i, essay_file in enumerate(essay_files):
            with open(essay_file, encoding="utf-8") as f:
                essay_content = f.read()

            try:
                storage_id = await service_manager.upload_content_directly(essay_content)
                essay_id = str(uuid.uuid4())  # Use standard UUID format (36 chars)

                essay_storage_refs.append(
                    {
                        "essay_id": essay_id,
                        "storage_id": storage_id,
                        "file_name": essay_file.split("/")[-1],
                    },
                )

                print(f"✅ Essay {i + 1} uploaded: {storage_id}")
            except RuntimeError as e:
                pytest.fail(f"Essay {i + 1} upload failed: {e}")

        # Step 2: Set up Kafka monitoring for CJ Assessment results using utility
        completed_topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
        failed_topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_FAILED)

        async with kafka_event_monitor(
            "cj_assessment_pipeline_test",
            [completed_topic, failed_topic],
        ) as consumer:
            # Step 3: Publish ELS_CJAssessmentRequestV1 event using utility
            cj_request = self._create_cj_assessment_request_event(
                batch_id=batch_id,
                essay_storage_refs=essay_storage_refs,
                correlation_id=correlation_id,
                language="en",
                course_code="SA24D ENG 5 WRITING 2025",
                essay_instructions="Write a persuasive essay on your topic.",
            )

            # Publish to the REQUEST topic (CJ Assessment Service listens here)
            request_topic = topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)
            try:
                await kafka_manager.publish_event(request_topic, cj_request)
                print(f"✅ Published CJ Assessment request for batch: {batch_id}")
            except RuntimeError as e:
                pytest.fail(f"CJ Assessment event publishing failed: {e}")

            # Step 4: Monitor for CJAssessmentCompletedV1 response using utility
            def cj_result_filter(event_data: dict[str, Any]) -> bool:
                """Filter for CJ assessment results from our specific test by correlation ID."""
                return "data" in event_data and event_data.get("correlation_id") == correlation_id

            try:
                # Wait for CJ assessment completion event
                events = await kafka_manager.collect_events(
                    consumer,
                    expected_count=1,
                    timeout_seconds=240,  # 4 minutes for CJ processing
                    event_filter=lambda event: (
                        event.get("event_type") == "huleedu.cj_assessment.completed.v1"
                        and event.get("correlation_id") == str(correlation_id)
                    ),
                )

                assert len(events) == 1, f"Expected 1 CJ assessment result, got {len(events)}"

                cj_completed_data = events[0]["data"]["data"]  # CJAssessmentCompletedV1 payload

                assert cj_completed_data["status"] == BatchStatus.COMPLETED_SUCCESSFULLY.value
                assert cj_completed_data["rankings"] is not None
                assert len(cj_completed_data["rankings"]) >= 2  # Should have rankings
                assert cj_completed_data["cj_assessment_job_id"] is not None

                print(
                    f"✅ CJ Assessment completed with job ID: "
                    f"{cj_completed_data['cj_assessment_job_id']}",
                )
                print(f"📊 Generated {len(cj_completed_data['rankings'])} essay rankings")

                # Step 5: Validate ranking structure and content
                rankings = cj_completed_data["rankings"]
                for i, ranking in enumerate(rankings):
                    assert "els_essay_id" in ranking
                    assert "rank" in ranking or "score" in ranking
                    print(f"📝 Essay {i + 1}: {ranking}")

                print("✅ CJ Assessment pipeline validation complete!")

            except Exception as e:
                pytest.fail(f"Event collection or validation failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_cj_assessment_pipeline_minimal_essays(self):
        """
        Test CJ Assessment pipeline with minimal number of essays.

        Uses modern utility patterns throughout.
        Validates that the pipeline works with just 2 essays (minimum for CJ).
        """
        service_manager = ServiceTestManager()
        correlation_id = str(uuid.uuid4())
        batch_id = str(uuid.uuid4())  # Use standard UUID format (36 chars) to match database schema

        # Use just 2 essays for minimal CJ
        essay_files = [
            "test_uploads/real_test_batch/MHHXGLUU 50 (SA24D ENG 5 WRITING 2025).txt",
            "test_uploads/real_test_batch/MHHXGLMX 50 (SA24D ENG 5 WRITING 2025).txt",
        ]

        # Upload essays using utility
        essay_storage_refs = []
        for i, essay_file in enumerate(essay_files):
            with open(essay_file, encoding="utf-8") as f:
                essay_content = f.read()

            try:
                storage_id = await service_manager.upload_content_directly(essay_content)
                essay_id = str(uuid.uuid4())  # Use standard UUID format (36 chars)

                essay_storage_refs.append({"essay_id": essay_id, "storage_id": storage_id})
            except RuntimeError as e:
                pytest.fail(f"Minimal essay {i + 1} upload failed: {e}")

        # Set up monitoring using utility
        completed_topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)

        async with kafka_event_monitor("minimal_cj_assessment_test", [completed_topic]) as consumer:
            # Publish event using utility
            cj_request = self._create_cj_assessment_request_event(
                batch_id=batch_id,
                essay_storage_refs=essay_storage_refs,
                correlation_id=correlation_id,
                language="en",
                course_code="TEST_COURSE_MINIMAL",
                essay_instructions="Write a short essay.",
            )

            # Publish to the REQUEST topic (CJ Assessment Service listens here)
            request_topic = topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)
            try:
                await kafka_manager.publish_event(request_topic, cj_request)
            except RuntimeError as e:
                pytest.fail(f"Minimal CJ Assessment event publishing failed: {e}")

            # Monitor for results using utility
            def cj_result_filter(event_data: dict[str, Any]) -> bool:
                """Filter for CJ assessment results from our specific test by correlation ID."""
                return "data" in event_data and event_data.get("correlation_id") == correlation_id

            try:
                events = await kafka_manager.collect_events(
                    consumer,
                    expected_count=1,
                    timeout_seconds=180,  # 3 minutes for minimal CJ processing
                    event_filter=cj_result_filter,
                )

                assert len(events) == 1

                # events[0] is the EventEnvelope, events[0]["data"] is the actual
                # CJAssessmentCompletedV1 payload
                event_envelope = events[0]
                cj_completed_data = event_envelope["data"]["data"]

                assert cj_completed_data["status"] == BatchStatus.COMPLETED_SUCCESSFULLY.value
                assert len(cj_completed_data["rankings"]) == 2  # Should rank both essays
                print("✅ Minimal CJ Assessment completed with 2 essays ranked")

            except Exception as e:
                pytest.fail(f"Minimal CJ Assessment validation failed: {e}")

    def _create_cj_assessment_request_event(
        self,
        batch_id: str,
        essay_storage_refs: list[dict[str, str]],
        correlation_id: str,
        language: str = "en",
        course_code: str = "TEST_COURSE",
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

        # Create EntityReference for the batch
        batch_entity_ref = EntityReference(entity_id=batch_id, entity_type="batch")

        # Create SystemProcessingMetadata (match original working implementation)
        system_metadata = SystemProcessingMetadata(
            entity=batch_entity_ref,
            timestamp=datetime.now(UTC),
            processing_stage=ProcessingStage.INITIALIZED,
            event=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED.value,
        )

        # Create the request data
        cj_request_data = ELS_CJAssessmentRequestV1(
            entity_ref=batch_entity_ref,
            system_metadata=system_metadata,
            essays_for_cj=essay_inputs,
            language=language,
            course_code=course_code,
            essay_instructions=essay_instructions,
            llm_config_overrides=None,  # Use service defaults
        )

        # Create EventEnvelope
        event_envelope = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type=topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED),
            event_timestamp=datetime.now(UTC),
            source_service="test_cj_assessment_workflows",
            correlation_id=uuid.UUID(correlation_id),
            data=cj_request_data,
        )

        # Convert to dict for Kafka publishing, serializing UUIDs to strings
        return event_envelope.model_dump(mode="json")
