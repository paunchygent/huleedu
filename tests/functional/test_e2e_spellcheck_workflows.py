"""
E2E Spellcheck Pipeline Workflows

Consolidated test suite for spellcheck pipeline validation, extracted and modernized from Step 4.
Tests complete spellcheck processing workflow from content upload through corrected results.

Uses modern utility patterns (ServiceTestManager + KafkaTestManager) throughout - NO direct calls.
Preserves all spellcheck business logic: pipeline validation,
correction counting, content verification.
"""

import uuid
from datetime import UTC
from typing import Any

import pytest

from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage
from tests.utils.kafka_test_manager import kafka_event_monitor, kafka_manager
from tests.utils.service_test_manager import ServiceTestManager


class TestE2ESpellcheckWorkflows:
    """Test spellcheck pipeline workflows using modern utility patterns exclusively."""

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_content_service_health_prerequisite(self):
        """Validate Content Service is healthy before spellcheck pipeline tests."""
        service_manager = ServiceTestManager()
        endpoints = await service_manager.get_validated_endpoints()

        if "content_service" not in endpoints:
            pytest.skip("Content Service not available for spellcheck testing")

        # Health validation is built into get_validated_endpoints()
        assert endpoints["content_service"]["status"] == "healthy"

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_spellchecker_service_health_prerequisite(self):
        """Validate Spell Checker Service metrics endpoint before spellcheck pipeline tests."""
        service_manager = ServiceTestManager()

        # Use utility to get metrics instead of direct HTTP call
        metrics_text = await service_manager.get_service_metrics("spellchecker_service", 8002)

        if metrics_text is None:
            pytest.skip("Spell Checker Service metrics not available")

        # Validate Prometheus metrics format
        assert "# HELP" in metrics_text or len(metrics_text.strip()) == 0

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    @pytest.mark.timeout(120)  # 2 minute timeout for complete spellcheck pipeline
    async def test_complete_spellcheck_processing_pipeline(self):
        """
        Test complete spellcheck pipeline: Content upload → Kafka event → Processing → Results

        Uses ServiceTestManager for Content Service interaction and KafkaTestManager for events.
        Validates the full business workflow:
        1. Upload test essay text to Content Service (via utility)
        2. Simulate SpellcheckRequestedV1 event (via utility)
        3. Monitor for SpellcheckResultDataV1 response (via utility)
        4. Validate corrected content stored in Content Service (via utility)
        """
        service_manager = ServiceTestManager()
        correlation_id = str(uuid.uuid4())
        essay_id = f"e2e-test-essay-{uuid.uuid4()}"

        # Test essay content with deliberate spelling errors
        test_essay_content = """
        This is a test esay with some speling errors that should be corrected.
        The spellchecker servic should identiy and fix these mistaks.
        We will valdiate that the correctd text is stored properley.
        """

        # Step 1: Upload original content to Content Service using utility
        try:
            original_storage_id = await service_manager.upload_content_directly(test_essay_content)
            print(f"✅ Original content uploaded with storage_id: {original_storage_id}")
        except RuntimeError as e:
            pytest.fail(f"Content upload failed: {e}")

        # Step 2: Set up Kafka monitoring for spellcheck results using utility
        result_topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED)

        async with kafka_event_monitor("spellcheck_pipeline_test", [result_topic]) as consumer:
            # Step 3: Publish SpellcheckRequestedV1 event using utility
            spellcheck_request = self._create_spellcheck_request_event(
                essay_id=essay_id,
                text_storage_id=original_storage_id,
                correlation_id=correlation_id,
                language="en",
            )

            # Publish to the REQUEST topic (spell checker listens here)
            request_topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
            try:
                await kafka_manager.publish_event(request_topic, spellcheck_request)
                print(f"✅ Published SpellcheckRequestedV1 event for essay: {essay_id}")
            except RuntimeError as e:
                pytest.fail(f"Event publishing failed: {e}")

            # Step 4: Monitor for SpellcheckResultDataV1 response using utility
            def spellcheck_result_filter(event_data: dict[str, Any]) -> bool:
                """Filter for spellcheck results from our specific essay."""
                return (
                    "data" in event_data
                    and event_data["data"].get("entity_ref", {}).get("entity_id") == essay_id
                    and event_data.get("correlation_id") == correlation_id
                )

            try:
                events = await kafka_manager.collect_events(
                    consumer,
                    expected_count=1,
                    timeout_seconds=90,
                    event_filter=spellcheck_result_filter,
                )

                assert len(events) == 1, f"Expected 1 spellcheck result, got {len(events)}"

                event_info = events[0]
                spellcheck_result = event_info["data"]["data"]  # SpellcheckResultDataV1 payload

                assert spellcheck_result["status"] == EssayStatus.SPELLCHECKED_SUCCESS.value
                assert spellcheck_result["corrections_made"] is not None
                assert spellcheck_result["corrections_made"] > 0  # Should have found errors
                print(
                    f"✅ Spellcheck completed with "
                    f"{spellcheck_result['corrections_made']} corrections",
                )

                # Step 5: Validate corrected content stored in Content Service using utility
                storage_metadata = spellcheck_result.get("storage_metadata", {})
                corrected_storage_id = (
                    storage_metadata.get("references", {}).get("corrected_text", {}).get("default")
                )

                assert corrected_storage_id is not None, (
                    f"No corrected text storage ID found in: {storage_metadata}"
                )
                print(f"📝 Found corrected text storage ID: {corrected_storage_id}")

                try:
                    corrected_content = await service_manager.fetch_content_directly(
                        corrected_storage_id,
                    )

                    assert corrected_content is not None
                    assert corrected_content != test_essay_content
                    assert "essay" in corrected_content
                    assert "spelling" in corrected_content
                    print("✅ Corrected content retrieved and validated")
                    print(
                        f"📝 Original length: {len(test_essay_content)}, "
                        f"Corrected length: {len(corrected_content)}",
                    )
                except RuntimeError as e:
                    pytest.fail(f"Content fetch failed: {e}")

            except Exception as e:
                pytest.fail(f"Event collection or validation failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_spellcheck_pipeline_with_no_errors(self):
        """
        Test spellcheck pipeline with text that has no spelling errors.

        Uses modern utility patterns throughout.
        Validates that the pipeline processes correctly even when no corrections are needed.
        """
        service_manager = ServiceTestManager()
        correlation_id = str(uuid.uuid4())
        essay_id = f"e2e-test-perfect-essay-{uuid.uuid4()}"

        # Perfect essay content with no spelling errors
        perfect_essay_content = """
        This is a perfectly written essay with no spelling errors.
        Every word is correctly spelled and the grammar is proper.
        The spellchecker service should find no corrections needed.
        """

        # Upload using utility
        try:
            original_storage_id = await service_manager.upload_content_directly(
                perfect_essay_content,
            )
        except RuntimeError as e:
            pytest.fail(f"Content upload failed: {e}")

        # Set up monitoring using utility
        result_topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED)

        async with kafka_event_monitor("perfect_spellcheck_test", [result_topic]) as consumer:
            # Publish event using utility
            spellcheck_request = self._create_spellcheck_request_event(
                essay_id=essay_id,
                text_storage_id=original_storage_id,
                correlation_id=correlation_id,
                language="en",
            )

            # Publish to the REQUEST topic (spell checker listens here)
            request_topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
            try:
                await kafka_manager.publish_event(request_topic, spellcheck_request)
            except RuntimeError as e:
                pytest.fail(f"Event publishing failed: {e}")

            # Monitor for results using utility
            def spellcheck_result_filter(event_data: dict[str, Any]) -> bool:
                """Filter for spellcheck results from our specific essay."""
                return (
                    "data" in event_data
                    and event_data["data"].get("entity_ref", {}).get("entity_id") == essay_id
                    and event_data.get("correlation_id") == correlation_id
                )

            try:
                events = await kafka_manager.collect_events(
                    consumer,
                    expected_count=1,
                    timeout_seconds=60,
                    event_filter=spellcheck_result_filter,
                )

                assert len(events) == 1
                spellcheck_result = events[0]["data"]["data"]

                assert spellcheck_result["status"] == EssayStatus.SPELLCHECKED_SUCCESS.value
                corrections_made = spellcheck_result["corrections_made"]
                assert corrections_made is not None
                assert corrections_made <= 2  # Should be minimal corrections for good text
                print(f"✅ Perfect text processed with {corrections_made} minimal corrections")

            except Exception as e:
                pytest.fail(f"Event collection or validation failed: {e}")

    def _create_spellcheck_request_event(
        self,
        essay_id: str,
        text_storage_id: str,
        correlation_id: str,
        language: str = "en",
    ) -> dict[str, Any]:
        """
        Create SpellcheckRequestedV1 event structure.

        Helper method that creates the proper EventEnvelope structure for spellcheck requests.
        """
        from datetime import datetime

        # Create entity reference for the essay
        essay_entity_ref = EntityReference(entity_id=essay_id, entity_type="essay")

        # Create system metadata (match original working implementation)
        system_metadata = SystemProcessingMetadata(
            entity=essay_entity_ref,
            timestamp=datetime.now(UTC),
            started_at=datetime.now(UTC),
            processing_stage=ProcessingStage.PROCESSING,
            event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
        )

        # Create the request data (match original working implementation)
        spellcheck_request_data = EssayLifecycleSpellcheckRequestV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            entity_ref=essay_entity_ref,
            timestamp=datetime.now(UTC),
            status=EssayStatus.AWAITING_SPELLCHECK,
            text_storage_id=text_storage_id,
            language=language,
            system_metadata=system_metadata,
        )

        # Create EventEnvelope
        event_envelope = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type="huleedu.essay.spellcheck.requested.v1",
            event_timestamp=datetime.now(UTC),
            source_service="test_spellcheck_workflows",
            correlation_id=uuid.UUID(correlation_id),
            data=spellcheck_request_data,
        )

        # Convert to dict for Kafka publishing, serializing UUIDs to strings
        return event_envelope.model_dump(mode="json")
