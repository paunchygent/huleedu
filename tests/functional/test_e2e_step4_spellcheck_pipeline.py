"""
End-to-End Test: Phase 4 - Spellcheck Pipeline Validation

This test validates the complete spellcheck processing pipeline:
1. Content upload to Content Service
2. SpellcheckRequestedV1 event simulation
3. Spell Checker Service processing
4. SpellcheckResultDataV1 event generation
5. Content Service corrected text storage

Follows the research-first, real-service testing pattern from phases 1-3.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import aiohttp
import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from common_core.enums import EssayStatus, ProcessingEvent, ProcessingStage, topic_name
from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EntityReference, SystemProcessingMetadata


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_content_service_health_prerequisite():
    """Validate Content Service is healthy before spellcheck pipeline tests."""
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:8001/healthz") as response:
            assert response.status == 200
            health_data = await response.json()
            assert health_data["status"] == "ok"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_spell_checker_service_health_prerequisite():
    """Validate Spell Checker Service metrics endpoint before spellcheck pipeline tests."""
    # Spell Checker is a worker service with metrics on port 8002
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:8002/metrics") as response:
            assert response.status == 200
            # Prometheus metrics format - should contain spell checker metrics
            metrics_text = await response.text()
            assert "kafka_message_queue_latency_seconds" in metrics_text


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(120)  # 2 minute timeout for complete spellcheck pipeline
async def test_complete_spellcheck_processing_pipeline():
    """
    Test complete spellcheck pipeline: Content upload → Kafka event → Processing → Results

    This test validates the full business workflow:
    1. Upload test essay text to Content Service
    2. Simulate SpellcheckRequestedV1 event (as BOS would send)
    3. Monitor for SpellcheckResultDataV1 response
    4. Validate corrected content stored in Content Service
    """
    correlation_id = str(uuid.uuid4())
    essay_id = f"e2e-test-essay-{uuid.uuid4()}"

    # Test essay content with deliberate spelling errors
    test_essay_content = """
    This is a test esay with some speling errors that should be corrected.
    The spellchecker servic should identiy and fix these mistaks.
    We will valdiate that the correctd text is stored properley.
    """

    # Step 1: Upload original content to Content Service
    original_storage_id = await upload_content_to_content_service(test_essay_content)
    assert original_storage_id is not None
    print(f"✅ Original content uploaded with storage_id: {original_storage_id}")

    # Step 2: Set up Kafka monitoring for spellcheck results
    result_topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED)
    result_consumer = AIOKafkaConsumer(
        result_topic,
        bootstrap_servers="localhost:9093",  # External port as learned in Phase 2
        group_id=f"e2e-test-spellcheck-consumer-{uuid.uuid4()}",
        auto_offset_reset="latest",  # Only new messages
        enable_auto_commit=False
    )

    try:
        await result_consumer.start()
        print(f"✅ Monitoring Kafka topic: {result_topic}")

        # Step 3: Publish SpellcheckRequestedV1 event (simulate BOS behavior)
        await publish_spellcheck_request_event(
            essay_id=essay_id,
            text_storage_id=original_storage_id,
            correlation_id=correlation_id,
            language="en"
        )
        print(f"✅ Published SpellcheckRequestedV1 event for essay: {essay_id}")

        # Step 4: Monitor for SpellcheckResultDataV1 response
        spellcheck_result = await monitor_for_spellcheck_result(
            result_consumer,
            essay_id=essay_id,
            correlation_id=correlation_id,
            timeout_seconds=90
        )

        assert spellcheck_result is not None
        assert spellcheck_result["status"] == EssayStatus.SPELLCHECKED_SUCCESS.value
        assert spellcheck_result["corrections_made"] is not None
        assert spellcheck_result["corrections_made"] > 0  # Should have found errors
        print(f"✅ Spellcheck completed with {spellcheck_result['corrections_made']} corrections")

        # Debug: Print the actual storage_metadata structure
        print(f"🔍 storage_metadata structure: "
              f"{spellcheck_result.get('storage_metadata', 'NOT_FOUND')}")

        # Step 5: Validate corrected content stored in Content Service
        # Based on actual structure: storage_metadata.references.corrected_text.default
        storage_metadata = spellcheck_result.get("storage_metadata", {})
        corrected_storage_id = storage_metadata.get("references", {}).get(
            "corrected_text", {}).get("default")

        assert corrected_storage_id is not None, (
            f"No corrected text storage ID found in: {storage_metadata}"
        )
        print(f"📝 Found corrected text storage ID: {corrected_storage_id}")

        corrected_content = await fetch_content_from_content_service(corrected_storage_id)

        assert corrected_content is not None
        assert corrected_content != test_essay_content  # Should be different from original
        assert "essay" in corrected_content  # "esay" should be corrected to "essay"
        assert "spelling" in corrected_content  # "speling" should be corrected to "spelling"
        print("✅ Corrected content retrieved and validated")
        print(f"📝 Original length: {len(test_essay_content)}, "
              f"Corrected length: {len(corrected_content)}")

    finally:
        await result_consumer.stop()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_spellcheck_pipeline_with_no_errors():
    """
    Test spellcheck pipeline with text that has no spelling errors.

    Validates that the pipeline processes correctly even when no corrections are needed.
    """
    correlation_id = str(uuid.uuid4())
    essay_id = f"e2e-test-perfect-essay-{uuid.uuid4()}"

    # Perfect essay content with no spelling errors
    perfect_essay_content = """
    This is a perfectly written essay with no spelling errors.
    Every word is correctly spelled and the grammar is proper.
    The spellchecker service should find no corrections needed.
    """

    # Upload and process
    original_storage_id = await upload_content_to_content_service(perfect_essay_content)

    # Set up monitoring
    result_topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED)
    result_consumer = AIOKafkaConsumer(
        result_topic,
        bootstrap_servers="localhost:9093",
        group_id=f"e2e-test-perfect-consumer-{uuid.uuid4()}",
        auto_offset_reset="latest",
        enable_auto_commit=False
    )

    try:
        await result_consumer.start()

        await publish_spellcheck_request_event(
            essay_id=essay_id,
            text_storage_id=original_storage_id,
            correlation_id=correlation_id,
            language="en"
        )

        spellcheck_result = await monitor_for_spellcheck_result(
            result_consumer,
            essay_id=essay_id,
            correlation_id=correlation_id,
            timeout_seconds=60
        )

        assert spellcheck_result is not None
        assert spellcheck_result["status"] == EssayStatus.SPELLCHECKED_SUCCESS.value
        # Note: The spell checker might find minor corrections even in "good" text
        corrections_made = spellcheck_result["corrections_made"]
        assert corrections_made is not None
        assert corrections_made <= 2  # Should be minimal corrections for good text
        print(f"✅ Perfect essay processed with {corrections_made} minimal corrections as expected")

    finally:
        await result_consumer.stop()


# Helper Functions (Research-based implementations)

async def upload_content_to_content_service(content: str) -> str:
    """Upload content to Content Service and return storage_id."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:8001/v1/content",
            data=content.encode('utf-8'),
            headers={"Content-Type": "text/plain"}
        ) as response:
            assert response.status == 201
            result = await response.json()
            storage_id: str = result["storage_id"]
            return storage_id


async def fetch_content_from_content_service(storage_id: str) -> str:
    """Fetch content from Content Service by storage_id."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://localhost:8001/v1/content/{storage_id}") as response:
            assert response.status == 200
            return await response.text()


async def publish_spellcheck_request_event(
    essay_id: str,
    text_storage_id: str,
    correlation_id: str,
    language: str = "en"
) -> None:
    """Publish SpellcheckRequestedV1 event to trigger spell checker processing."""

    # Create event data following common_core contracts
    entity_ref = EntityReference(entity_id=essay_id, entity_type="essay")

    system_metadata = SystemProcessingMetadata(
        entity=entity_ref,
        timestamp=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        processing_stage=ProcessingStage.PROCESSING,
        event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value
    )

    spellcheck_request_data = EssayLifecycleSpellcheckRequestV1(
        event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
        entity_ref=entity_ref,
        timestamp=datetime.now(timezone.utc),
        status=EssayStatus.AWAITING_SPELLCHECK,  # Required field from ProcessingUpdate
        text_storage_id=text_storage_id,
        language=language,
        system_metadata=system_metadata
    )

    # Create EventEnvelope
    event_envelope = EventEnvelope(
        event_type=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED),
        source_service="e2e-test-service",
        correlation_id=uuid.UUID(correlation_id),
        data=spellcheck_request_data
    )

    # Publish to Kafka
    request_topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
    producer = AIOKafkaProducer(bootstrap_servers="localhost:9093")

    try:
        await producer.start()
        message_value = json.dumps(event_envelope.model_dump(mode="json")).encode('utf-8')
        await producer.send_and_wait(
            request_topic,
            value=message_value,
            key=essay_id.encode('utf-8')
        )
    finally:
        await producer.stop()


async def monitor_for_spellcheck_result(
    consumer: AIOKafkaConsumer,
    essay_id: str,
    correlation_id: str,
    timeout_seconds: int = 90
) -> Optional[Dict[str, Any]]:
    """Monitor Kafka for SpellcheckResultDataV1 event matching essay_id and correlation_id."""

    end_time = datetime.now(timezone.utc).timestamp() + timeout_seconds

    while datetime.now(timezone.utc).timestamp() < end_time:
        try:
            # Poll for messages with 1 second timeout
            msg_batch = await consumer.getmany(timeout_ms=1000, max_records=10)

            for topic_partition, messages in msg_batch.items():
                for message in messages:
                    try:
                        # Parse EventEnvelope
                        message_text = message.value.decode('utf-8')
                        envelope_data = json.loads(message_text)

                        # Check if this is our essay's result
                        if (envelope_data.get("correlation_id") == correlation_id and
                            envelope_data.get("data", {}).get(
                                "entity_ref", {}).get("entity_id") == essay_id):

                            result_data: Dict[str, Any] = envelope_data["data"]
                            print(f"📨 Received spellcheck result for essay {essay_id}")
                            return result_data

                    except (json.JSONDecodeError, KeyError) as e:
                        print(f"⚠️  Failed to parse message: {e}")
                        continue

            # Brief sleep before next poll
            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"⚠️  Error during Kafka monitoring: {e}")
            await asyncio.sleep(1)

    print(f"⏰ Timeout waiting for spellcheck result for essay {essay_id}")
    return None
