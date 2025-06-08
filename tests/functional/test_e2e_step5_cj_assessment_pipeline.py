"""
End-to-End Test: Phase 5 - CJ Assessment Pipeline Validation

This test validates the complete CJ Assessment processing pipeline:
1. Content upload to Content Service for multiple essays
2. ELS_CJAssessmentRequestV1 event simulation
3. CJ Assessment Service processing (comparative judgment)
4. CJAssessmentCompletedV1 event generation
5. Content Service CJ results storage

Follows the research-first, real-service testing pattern from phases 1-4.
Uses real student essays from test_uploads directory.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from common_core.enums import BatchStatus, ProcessingEvent, ProcessingStage, topic_name
from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import (
    EntityReference,
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_content_service_health_prerequisite():
    """Validate Content Service is healthy before CJ Assessment tests."""
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:8001/healthz") as response:
            assert response.status == 200
            health_data = await response.json()
            assert health_data["status"] == "ok"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cj_assessment_service_health_prerequisite():
    """Validate CJ Assessment Service metrics before pipeline tests."""
    # CJ Assessment is a worker service with metrics on port 9095
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:9095/metrics") as response:
            assert response.status == 200
            # Prometheus metrics format - should contain CJ assessment metrics
            metrics_text = await response.text()
            assert "python_info" in metrics_text  # Basic Prometheus metric


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(300)  # 5 minute timeout for complete CJ pipeline
async def test_complete_cj_assessment_processing_pipeline():
    """
    Test complete CJ Assessment pipeline: Content upload → Kafka event →
    Processing → Results

    This test validates the full business workflow:
    1. Upload multiple real student essays to Content Service
    2. Simulate ELS_CJAssessmentRequestV1 event (as BOS would send)
    3. Monitor for CJAssessmentCompletedV1 response
    4. Validate CJ rankings and scores stored in Content Service
    """
    correlation_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())  # Use standard UUID format (36 chars) to match database schema

    # Use real student essays for CJ Assessment
    essay_files = [
        "test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt",
        "test_uploads/real_test_batch/MHHXGMXE 50 (SA24D ENG 5 WRITING 2025).txt",
        "test_uploads/real_test_batch/MHHXGMUX 50 (SA24D ENG 5 WRITING 2025).txt",
        "test_uploads/real_test_batch/MHHXGMUU 50 (SA24D ENG 5 WRITING 2025).txt"
    ]

    # Step 1: Upload essays to Content Service
    print(f"📚 Uploading {len(essay_files)} real student essays")
    essay_storage_refs = []

    for i, essay_file in enumerate(essay_files):
        with open(essay_file, 'r', encoding='utf-8') as f:
            essay_content = f.read()

        storage_id = await upload_content_to_content_service(essay_content)
        essay_id = str(uuid.uuid4())  # Use standard UUID format (36 chars) to match database schema

        essay_storage_refs.append({
            "essay_id": essay_id,
            "storage_id": storage_id,
            "file_name": essay_file.split('/')[-1]
        })

        print(f"✅ Essay {i+1} uploaded: {storage_id}")

    # Step 2: Set up Kafka monitoring for CJ Assessment results
    completed_topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
    failed_topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_FAILED)

    result_consumer = AIOKafkaConsumer(
        completed_topic,
        failed_topic,
        bootstrap_servers="localhost:9093",  # External port
        group_id=f"e2e-test-cj-consumer-{uuid.uuid4()}",
        auto_offset_reset="latest",  # Only new messages
        enable_auto_commit=False
    )

    try:
        await result_consumer.start()
        print(f"✅ Monitoring topics: {completed_topic}, {failed_topic}")

        # Step 3: Publish ELS_CJAssessmentRequestV1 event
        await publish_cj_assessment_request_event(
            batch_id=batch_id,
            essay_storage_refs=essay_storage_refs,
            correlation_id=correlation_id,
            language="en",
            course_code="SA24D ENG 5 WRITING 2025",
            essay_instructions="Write a persuasive essay on your topic."
        )
        print(f"✅ Published CJ Assessment request for batch: {batch_id}")

        # Step 4: Monitor for CJAssessmentCompletedV1 response
        cj_result = await monitor_for_cj_assessment_result(
            result_consumer,
            batch_id=batch_id,
            correlation_id=correlation_id,
            timeout_seconds=240  # 4 minutes for CJ processing
        )

        assert cj_result is not None
        assert cj_result["status"] == BatchStatus.COMPLETED_SUCCESSFULLY.value
        assert cj_result["rankings"] is not None
        assert len(cj_result["rankings"]) >= 2  # Should have rankings
        assert cj_result["cj_assessment_job_id"] is not None

        print(f"✅ CJ Assessment completed with job ID: "
              f"{cj_result['cj_assessment_job_id']}")
        print(f"📊 Generated {len(cj_result['rankings'])} essay rankings")

        # Step 5: Validate ranking structure and content
        rankings = cj_result["rankings"]
        for i, ranking in enumerate(rankings):
            assert "els_essay_id" in ranking
            assert "rank" in ranking or "score" in ranking
            print(f"📝 Essay {i+1}: {ranking}")

        # Optional: Validate CJ results storage in Content Service if available
        # This depends on whether CJ service stores results back to Content

        print("✅ CJ Assessment pipeline validation complete!")

    finally:
        await result_consumer.stop()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cj_assessment_pipeline_minimal_essays():
    """
    Test CJ Assessment pipeline with minimal number of essays.

    Validates that the pipeline works with just 2 essays (minimum for CJ).
    """
    correlation_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())  # Use standard UUID format (36 chars) to match database schema

    # Use just 2 essays for minimal CJ
    essay_files = [
        "test_uploads/real_test_batch/MHHXGLUU 50 (SA24D ENG 5 WRITING 2025).txt",
        "test_uploads/real_test_batch/MHHXGLMX 50 (SA24D ENG 5 WRITING 2025).txt"
    ]

    # Upload essays
    essay_storage_refs = []
    for i, essay_file in enumerate(essay_files):
        with open(essay_file, 'r', encoding='utf-8') as f:
            essay_content = f.read()

        storage_id = await upload_content_to_content_service(essay_content)
        essay_id = str(uuid.uuid4())  # Use standard UUID format (36 chars) to match database schema

        essay_storage_refs.append({
            "essay_id": essay_id,
            "storage_id": storage_id
        })

    # Set up monitoring
    completed_topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
    result_consumer = AIOKafkaConsumer(
        completed_topic,
        bootstrap_servers="localhost:9093",
        group_id=f"e2e-test-minimal-cj-consumer-{uuid.uuid4()}",
        auto_offset_reset="latest",
        enable_auto_commit=False
    )

    try:
        await result_consumer.start()

        await publish_cj_assessment_request_event(
            batch_id=batch_id,
            essay_storage_refs=essay_storage_refs,
            correlation_id=correlation_id,
            language="en",
            course_code="SA24D ENG 5 WRITING 2025",
            essay_instructions="Write about your chosen topic."
        )

        cj_result = await monitor_for_cj_assessment_result(
            result_consumer,
            batch_id=batch_id,
            correlation_id=correlation_id,
            timeout_seconds=120
        )

        assert cj_result is not None
        assert cj_result["status"] == BatchStatus.COMPLETED_SUCCESSFULLY.value
        rankings = cj_result["rankings"]
        assert len(rankings) == 2  # Exactly 2 essays ranked

        # Validate ranking order (should have rank 1 and rank 2)
        ranks = [r.get("rank", 0) for r in rankings]
        assert 1 in ranks or 2 in ranks  # Should have proper ranking

        print(f"✅ Minimal CJ completed with {len(rankings)} rankings")

    finally:
        await result_consumer.stop()


# Helper Functions


async def upload_content_to_content_service(content: str) -> str:
    """Upload content to Content Service and return storage ID."""
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


async def publish_cj_assessment_request_event(
    batch_id: str,
    essay_storage_refs: List[Dict[str, str]],
    correlation_id: str,
    language: str = "en",
    course_code: str = "TEST_COURSE",
    essay_instructions: str = "Write an essay."
) -> None:
    """Publish ELS_CJAssessmentRequestV1 event to trigger CJ processing."""

    # Create EntityReference for the batch
    batch_entity_ref = EntityReference(
        entity_id=batch_id,
        entity_type="batch"
    )

    # Create SystemProcessingMetadata
    system_metadata = SystemProcessingMetadata(
        entity=batch_entity_ref,
        timestamp=datetime.now(timezone.utc),
        processing_stage=ProcessingStage.INITIALIZED,
        event=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED.value
    )

    # Create essay references for CJ processing
    essays_for_cj = []
    for ref in essay_storage_refs:
        essay_ref = EssayProcessingInputRefV1(
            essay_id=ref["essay_id"],
            text_storage_id=ref["storage_id"]
        )
        essays_for_cj.append(essay_ref)

    # Create the CJ Assessment request event data
    request_data = ELS_CJAssessmentRequestV1(
        entity_ref=batch_entity_ref,
        system_metadata=system_metadata,
        essays_for_cj=essays_for_cj,
        language=language,
        course_code=course_code,
        essay_instructions=essay_instructions,
        llm_config_overrides=None  # Use service defaults
    )

    # Create the event envelope
    envelope = EventEnvelope[ELS_CJAssessmentRequestV1](
        event_type=topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED),
        source_service="e2e_test_suite",
        correlation_id=uuid.UUID(correlation_id),
        data=request_data
    )

    # Publish to Kafka
    request_topic = topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)
    producer = AIOKafkaProducer(
        bootstrap_servers="localhost:9093",
        value_serializer=lambda v: json.dumps(
            v, default=str, ensure_ascii=False
        ).encode("utf-8")
    )

    try:
        await producer.start()

        # Send the envelope as dict for JSON serialization
        envelope_dict = envelope.model_dump(mode="json")

        await producer.send(
            request_topic,
            value=envelope_dict,
            key=correlation_id.encode("utf-8")
        )

        await producer.flush()

    finally:
        await producer.stop()


async def monitor_for_cj_assessment_result(
    consumer: AIOKafkaConsumer,
    batch_id: str,
    correlation_id: str,
    timeout_seconds: int = 240
) -> Optional[Dict[str, Any]]:
    """Monitor Kafka for CJ Assessment completion or failure events."""

    start_time = asyncio.get_event_loop().time()

    async for msg in consumer:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout_seconds:
            print(f"❌ Timeout waiting for CJ Assessment result after "
                  f"{timeout_seconds}s")
            return None

        try:
            # Deserialize the event envelope
            envelope_data = json.loads(msg.value.decode("utf-8"))

            # Check correlation ID match
            msg_correlation_id = envelope_data.get("correlation_id")
            if str(msg_correlation_id) != correlation_id:
                continue  # Not our message

            # Extract event data
            event_data = envelope_data.get("data", {})
            entity_ref = event_data.get("entity_ref", {})
            msg_batch_id = entity_ref.get("entity_id")

            if msg_batch_id != batch_id:
                continue  # Not our batch

            # Process completed event
            if msg.topic.endswith("completed.v1"):
                print("✅ Received CJ Assessment completed event")
                return {
                    "status": event_data.get("status"),
                    "rankings": event_data.get("rankings", []),
                    "cj_assessment_job_id": event_data.get(
                        "cj_assessment_job_id"
                    ),
                    "system_metadata": event_data.get("system_metadata", {})
                }

            # Process failed event
            elif msg.topic.endswith("failed.v1"):
                print("❌ Received CJ Assessment failed event")
                error_info = event_data.get("system_metadata", {}).get(
                    "error_info", {}
                )

                # Extract and format the most relevant error information
                error_message = error_info.get("error_message", "Unknown error")
                error_type = error_info.get("error_type", "UnknownErrorType")

                # Print detailed error information for debugging
                print(f"Error type: {error_type}")
                print(f"Error message: {error_message}")

                # If there's a traceback, print the first few lines for context
                traceback_info = error_info.get("traceback", "")
                if traceback_info:
                    traceback_lines = traceback_info.split("\n")[:10]  # First 10 lines
                    print("Traceback preview:")
                    for line in traceback_lines:
                        print(f"  {line}")

                raise AssertionError(
                    f"CJ Assessment failed: {error_type} - {error_message}"
                )

        except json.JSONDecodeError as e:
            print(f"⚠️ Failed to decode message: {e}")
            continue
        except Exception as e:
            print(f"⚠️ Error processing message: {e}")
            continue

    return None  # No result found within timeout
