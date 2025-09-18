"""
E2E Spellcheck Pipeline Workflows

Consolidated test suite for spellcheck pipeline validation, extracted and modernized from Step 4.
Tests complete spellcheck processing workflow from content upload through corrected results.

Uses modern utility patterns (ServiceTestManager + KafkaTestManager) throughout - NO direct calls.
Preserves all spellcheck business logic: pipeline validation,
correction counting, content verification.
"""

from __future__ import annotations

# Use a local Kafka producer fixture following known working patterns
import json
import uuid
from datetime import UTC
from typing import Any

import pytest
import pytest_asyncio
from aiokafka import AIOKafkaProducer
from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage

from tests.utils.kafka_test_manager import kafka_manager
from tests.utils.service_test_manager import ServiceTestManager


@pytest_asyncio.fixture
async def kafka_producer_for_e2e() -> AIOKafkaProducer:
    """Local Kafka producer using the same pattern as working integration fixtures.

    Uses external listener (localhost:9093), JSON value serialization, and
    conservative delivery guarantees to avoid in-flight ordering issues.
    """
    # Mirror working functional/integration pattern: JSON serializer + send+flush
    producer = AIOKafkaProducer(
        bootstrap_servers="localhost:9093",
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    await producer.start()
    try:
        yield producer
    finally:
        await producer.stop()


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
    async def test_complete_spellcheck_processing_pipeline(
        self, kafka_producer_for_e2e: AIOKafkaProducer
    ):
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
        batch_id = f"e2e-test-batch-{uuid.uuid4()}"

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
        # Updated to listen to actual topic that spellchecker publishes to (thin event)
        result_topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)

        # Use explicit consumer with 'earliest' to avoid any edge-case race
        async with kafka_manager.consumer(
            "spellcheck_pipeline_test",
            [result_topic, topic_name(ProcessingEvent.SPELLCHECK_RESULTS)],
            auto_offset_reset="earliest",
        ) as consumer:
            # Step 3: Publish SpellcheckRequestedV1 event using utility
            spellcheck_request = self._create_spellcheck_request_event(
                essay_id=essay_id,
                text_storage_id=original_storage_id,
                correlation_id=correlation_id,
                batch_id=batch_id,
                language="en",
            )

            # Publish to the REQUEST topic (spell checker listens here)
            request_topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
            try:
                # Publish dict payload with JSON value_serializer and capture RecordMetadata
                record_md = await kafka_producer_for_e2e.send_and_wait(
                    request_topic,
                    spellcheck_request,
                    key=essay_id.encode("utf-8"),
                )
                print(
                    "✅ Published SpellcheckRequestedV1",
                    f"topic={getattr(record_md, 'topic', request_topic)}",
                    f"partition={getattr(record_md, 'partition', 'n/a')}",
                    f"offset={getattr(record_md, 'offset', 'n/a')}",
                    f"essay_id={essay_id}",
                    f"correlation_id={correlation_id}",
                )
            except Exception as e:
                pytest.fail(f"Event publishing failed: {e}")

            # Step 4: Monitor for SpellcheckPhaseCompletedV1 response using utility
            def spellcheck_result_filter(event_data: dict[str, Any]) -> bool:
                """Filter for spellcheck results from our specific essay.

                This operates on the raw EventEnvelope dict; the payload is under
                envelope["data"], not nested twice.
                """
                payload = event_data.get("data", {}) or {}
                corr = payload.get("correlation_id") or event_data.get("correlation_id")
                return payload.get("entity_id") == essay_id and corr == correlation_id

            try:
                events = await kafka_manager.collect_events(
                    consumer,
                    expected_count=1,
                    timeout_seconds=90,
                    event_filter=spellcheck_result_filter,
                )

                assert len(events) == 1, f"Expected 1 spellcheck result, got {len(events)}"

                event_info = events[0]
                spellcheck_result = event_info["data"][
                    "data"
                ]  # EventEnvelope.data contains SpellcheckPhaseCompletedV1

                # SpellcheckPhaseCompletedV1 uses ProcessingStatus enum
                from common_core.status_enums import ProcessingStatus

                assert spellcheck_result["status"] == ProcessingStatus.COMPLETED.value
                assert spellcheck_result["corrected_text_storage_id"] is not None
                print(f"✅ Spellcheck completed in {spellcheck_result['processing_duration_ms']}ms")

                # Step 5: Validate corrected content stored in Content Service using utility
                corrected_storage_id = spellcheck_result["corrected_text_storage_id"]

                assert corrected_storage_id is not None, (
                    "No corrected text storage ID found in event payload"
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
    async def test_spellcheck_pipeline_with_no_errors(
        self, kafka_producer_for_e2e: AIOKafkaProducer
    ):
        """
        Test spellcheck pipeline with text that has no spelling errors.

        Uses modern utility patterns throughout.
        Validates that the pipeline processes correctly even when no corrections are needed.
        """
        service_manager = ServiceTestManager()
        correlation_id = str(uuid.uuid4())
        essay_id = f"e2e-test-perfect-essay-{uuid.uuid4()}"
        batch_id = f"e2e-test-perfect-batch-{uuid.uuid4()}"

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
        # Updated to listen to actual topic that spellchecker publishes to (thin event)
        result_topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)

        async with kafka_manager.consumer(
            "perfect_spellcheck_test",
            [result_topic, topic_name(ProcessingEvent.SPELLCHECK_RESULTS)],
            auto_offset_reset="earliest",
        ) as consumer:
            # Publish event using utility
            spellcheck_request = self._create_spellcheck_request_event(
                essay_id=essay_id,
                text_storage_id=original_storage_id,
                correlation_id=correlation_id,
                batch_id=batch_id,
                language="en",
            )

            # Publish to the REQUEST topic (spell checker listens here)
            request_topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
            try:
                record_md = await kafka_producer_for_e2e.send_and_wait(
                    request_topic,
                    spellcheck_request,
                    key=essay_id.encode("utf-8"),
                )
                print(
                    "✅ Published SpellcheckRequestedV1",
                    f"topic={getattr(record_md, 'topic', request_topic)}",
                    f"partition={getattr(record_md, 'partition', 'n/a')}",
                    f"offset={getattr(record_md, 'offset', 'n/a')}",
                    f"essay_id={essay_id}",
                    f"correlation_id={correlation_id}",
                )
            except Exception as e:
                pytest.fail(f"Event publishing failed: {e}")

            # Monitor for results using utility
            def spellcheck_result_filter(event_data: dict[str, Any]) -> bool:
                """Filter for spellcheck results from our specific essay.

                Operates on raw EventEnvelope dict; payload is envelope["data"].
                """
                payload = event_data.get("data", {}) or {}
                corr = payload.get("correlation_id") or event_data.get("correlation_id")
                return payload.get("entity_id") == essay_id and corr == correlation_id

            try:
                events = await kafka_manager.collect_events(
                    consumer,
                    expected_count=1,
                    timeout_seconds=60,
                    event_filter=spellcheck_result_filter,
                )

                assert len(events) == 1
                spellcheck_result = events[0]["data"][
                    "data"
                ]  # EventEnvelope.data contains SpellcheckPhaseCompletedV1

                # SpellcheckPhaseCompletedV1 uses ProcessingStatus enum
                from common_core.status_enums import ProcessingStatus

                assert spellcheck_result["status"] == ProcessingStatus.COMPLETED.value
                processing_duration = spellcheck_result["processing_duration_ms"]
                assert processing_duration is not None
                # Extremely fast runs can legitimately be 0ms after int() rounding
                assert processing_duration >= 0
                print(f"✅ Perfect text processed in {processing_duration}ms")

            except Exception as e:
                pytest.fail(f"Event collection or validation failed: {e}")

    def _create_spellcheck_request_event(
        self,
        essay_id: str,
        text_storage_id: str,
        correlation_id: str,
        batch_id: str,
        language: str = "en",
    ) -> dict[str, Any]:
        """
        Create SpellcheckRequestedV1 event structure.

        Helper method that creates the proper EventEnvelope structure for spellcheck requests.
        """
        from datetime import datetime

        # Create system metadata (match original working implementation)
        system_metadata = SystemProcessingMetadata(
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id,
            timestamp=datetime.now(UTC),
            started_at=datetime.now(UTC),
            processing_stage=ProcessingStage.PROCESSING,
            event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
        )

        # Create the request data (match original working implementation)
        spellcheck_request_data = EssayLifecycleSpellcheckRequestV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id,
            timestamp=datetime.now(UTC),
            status=EssayStatus.AWAITING_SPELLCHECK,
            text_storage_id=text_storage_id,
            language=language,
            system_metadata=system_metadata,
        )

        # Create EventEnvelope
        event_envelope: EventEnvelope[EssayLifecycleSpellcheckRequestV1] = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type="huleedu.essay.spellcheck.requested.v1",
            event_timestamp=datetime.now(UTC),
            source_service="test_spellcheck_workflows",
            correlation_id=uuid.UUID(correlation_id),
            data=spellcheck_request_data,
        )

        # Convert to dict for Kafka publishing, serializing UUIDs to strings
        return event_envelope.model_dump(mode="json")
