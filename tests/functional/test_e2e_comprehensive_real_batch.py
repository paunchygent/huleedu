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

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

import aiohttp
import pytest
from aiokafka import AIOKafkaConsumer

from common_core.enums import ProcessingEvent, topic_name


@pytest.mark.e2e
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
    """
    # Validate real test essays are available
    real_test_dir = Path("test_uploads/real_test_batch")
    if not real_test_dir.exists():
        pytest.skip("Real test batch directory not found")

    essay_files = list(real_test_dir.glob("*.txt"))
    if len(essay_files) < 2:
        pytest.skip("Need at least 2 real essays for comprehensive test")

    print(f"📚 Found {len(essay_files)} real student essays")

    # Use subset for test performance
    test_essays = essay_files[:25]

    # Step 1: Validate all services are healthy
    await validate_all_services_healthy()

    # Step 2: Set up Kafka consumer for pipeline events FIRST
    consumer_group_id = f"e2e-comprehensive-test-{uuid.uuid4().hex[:8]}"
    monitoring_topics = [
        topic_name(ProcessingEvent.BATCH_ESSAYS_READY),
        topic_name(ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND),
        topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME),
        topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        topic_name(ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND),
        topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
    ]

    event_consumer = AIOKafkaConsumer(
        *monitoring_topics,
        bootstrap_servers="localhost:9093",
        group_id=consumer_group_id,
        auto_offset_reset="latest",
        enable_auto_commit=False,
        value_deserializer=lambda x: json.loads(x.decode("utf-8")),
    )

    try:
        await event_consumer.start()
        print("✅ Consumer starting...")

        # FIX: Wait for the consumer to be assigned partitions, then seek to the end.
        # This robustly prevents the race condition where events are published before the
        # consumer is ready to read from the 'latest' position.
        partitions_assigned = False
        assignment_timeout = 15  # seconds
        start_time = asyncio.get_event_loop().time()
        while not partitions_assigned:
            if asyncio.get_event_loop().time() - start_time > assignment_timeout:
                pytest.fail("Kafka consumer did not get partition assignment within timeout.")

            assigned_partitions = event_consumer.assignment()
            if assigned_partitions:
                print(f"✅ Consumer assigned partitions: {assigned_partitions}")
                # Now that we have partitions, seek to the absolute end of them.
                await event_consumer.seek_to_end()
                print("✅ Consumer is now positioned at the end of all topics.")
                partitions_assigned = True
            else:
                # Still waiting for the consumer group to balance and assign partitions.
                await asyncio.sleep(0.2)

        # Step 3: Generate a valid UUID for the correlation ID
        test_correlation_id = str(uuid.uuid4())
        print(f"🔍 Test correlation ID: {test_correlation_id}")

        # Step 4: Register batch with BOS
        print("📝 Registering batch with BOS to create essay slots...")
        batch_id = await register_batch_with_bos(len(test_essays), test_correlation_id)
        print(f"✅ Batch registered with BOS: {batch_id}")

        # Step 5: Upload files to trigger the pipeline
        print("🚀 Uploading real student essays to trigger pipeline...")
        upload_response = await upload_real_essays_via_file_service(
            batch_id=batch_id, essay_files=test_essays, correlation_id=test_correlation_id
        )
        print(f"✅ File upload successful: {upload_response}")

        # Step 6: Watch pipeline progression
        print("⏳ Watching pipeline progression...")
        result = await watch_pipeline_progression(
            event_consumer, batch_id, test_correlation_id, timeout_seconds=180
        )
        cj_completion = result

        assert cj_completion is not None, "CJ assessment phase did not complete"
        print(f"✅ CJ assessment completed for batch: {batch_id}")

        # Validate we got rankings
        cj_data = cj_completion.get("data", {})
        rankings = cj_data.get("rankings", [])
        assert len(rankings) >= 1, f"Expected at least one ranking, got {len(rankings)}"

        print(f"🎯 Complete pipeline success! Generated {len(rankings)} essay rankings")

    finally:
        await event_consumer.stop()


async def validate_all_services_healthy() -> None:
    """Validate all services are healthy before running comprehensive test."""
    services = [
        ("File Service", "http://localhost:7001/healthz"),
        ("Content Service", "http://localhost:8001/healthz"),
        ("ELS API", "http://localhost:6001/healthz"),
        ("BOS", "http://localhost:5001/healthz"),
        ("Spell Checker (metrics)", "http://localhost:8002/metrics"),
        ("CJ Assessment (metrics)", "http://localhost:9095/metrics"),
    ]

    async with aiohttp.ClientSession() as session:
        for service_name, url in services:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status in [200, 202]:
                        print(f"✅ {service_name} healthy")
                    else:
                        raise AssertionError(f"{service_name} unhealthy: {response.status}")
            except Exception as e:
                raise AssertionError(f"{service_name} health check failed: {e}")


async def upload_real_essays_via_file_service(
    batch_id: str, essay_files: List[Path], correlation_id: str | None = None
) -> Dict[str, Any]:
    """Upload real student essays via File Service batch endpoint."""

    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        data.add_field("batch_id", batch_id)

        for essay_file in essay_files:
            essay_content = essay_file.read_text(encoding="utf-8")
            data.add_field(
                "files", essay_content, filename=essay_file.name, content_type="text/plain"
            )

        headers = {}
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        async with session.post(
            "http://localhost:7001/v1/files/batch",
            data=data,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as response:
            if response.status == 202:
                result: Dict[str, Any] = await response.json()
                return result
            else:
                error_text = await response.text()
                raise AssertionError(f"File upload failed: {response.status} - {error_text}")


async def register_batch_with_bos(
    expected_essay_count: int, correlation_id: str | None = None
) -> str:
    """Register a batch with BOS to create essay slots before file upload."""

    registration_payload = {
        "expected_essay_count": expected_essay_count,
        "course_code": "ENG5",
        "class_designation": "E2E-Test-Class",
        "essay_instructions": "End-to-end test essay for comprehensive pipeline validation",
        "teacher_name": "E2E Test Teacher",
        "enable_cj_assessment": True,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:5001/v1/batches/register",
            json=registration_payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            if response.status == 202:
                result: Dict[str, Any] = await response.json()
                batch_id: str = result["batch_id"]
                return batch_id
            else:
                error_text = await response.text()
                raise AssertionError(
                    f"BOS batch registration failed: {response.status} - {error_text}"
                )


async def watch_pipeline_progression(
    consumer: AIOKafkaConsumer,
    batch_id: str,
    correlation_id: str | None = None,
    timeout_seconds: int = 180,
) -> Dict[str, Any] | None:
    """Watch pipeline progression and wait for completion."""

    start_time = asyncio.get_event_loop().time()
    end_time = start_time + timeout_seconds

    while asyncio.get_event_loop().time() < end_time:
        try:
            msg_batch = await consumer.getmany(timeout_ms=1000, max_records=10)

            for topic_partition, messages in msg_batch.items():
                for message in messages:
                    try:
                        envelope_data = message.value
                        event_data = envelope_data.get("data", {})
                        event_correlation_id = envelope_data.get("correlation_id")

                        # Primary filter: correlation_id MUST match.
                        if correlation_id is None or event_correlation_id != correlation_id:
                            continue

                        # Secondary check: entity_id should match for batch-level events.
                        # For essay-level events, this check is skipped as we rely on
                        # correlation_id.
                        entity_match = False

                        # List of topics that are about the whole batch
                        batch_level_topics = [
                            topic_name(ProcessingEvent.BATCH_ESSAYS_READY),
                            topic_name(ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND),
                            topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME),
                            topic_name(ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND),
                            topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
                        ]

                        if message.topic in batch_level_topics:
                            entity_id_from_event = None
                            if message.topic == topic_name(ProcessingEvent.BATCH_ESSAYS_READY):
                                entity_id_from_event = event_data.get("batch_id")
                            else:
                                entity_id_from_event = event_data.get("entity_ref", {}).get(
                                    "entity_id"
                                )

                            if entity_id_from_event == batch_id:
                                entity_match = True
                        elif message.topic == topic_name(
                            ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED
                        ):
                            # This is an essay-level event. The correlation_id match is sufficient.
                            entity_match = True
                        else:
                            # Skip topics not relevant to this test's flow
                            continue

                        if entity_match:
                            if message.topic == topic_name(ProcessingEvent.BATCH_ESSAYS_READY):
                                essay_count = len(event_data.get("ready_essays", []))
                                print(
                                    (
                                        f"📨 1️⃣ ELS published BatchEssaysReady: "
                                        f"{essay_count} essays ready"
                                    )
                                )
                            elif message.topic == topic_name(
                                ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND
                            ):
                                print("📨 2️⃣ BOS published spellcheck initiate command")
                            elif message.topic == topic_name(
                                ProcessingEvent.ELS_BATCH_PHASE_OUTCOME
                            ):
                                print(
                                    (
                                        f"📨 3️⃣ ELS published phase outcome: "
                                        f"{event_data.get('phase_name')} -> "
                                        f"{event_data.get('phase_status')}"
                                    )
                                )
                            elif message.topic == topic_name(
                                ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND
                            ):
                                essay_count = len(event_data.get("essays_to_process", []))
                                print(
                                    (
                                        f"📨 4️⃣ BOS published CJ assessment initiate command: "
                                        f"{essay_count} essays"
                                    )
                                )
                            elif message.topic == topic_name(
                                ProcessingEvent.CJ_ASSESSMENT_COMPLETED
                            ):
                                rankings = event_data.get("rankings", [])
                                print(
                                    f"📨 5️⃣ CJ assessment completed: {len(rankings)} essays ranked"
                                )
                                print(
                                    "🎯 Pipeline SUCCESS! Complete end-to-end processing finished."
                                )
                                return dict(envelope_data)

                    except (json.JSONDecodeError, KeyError) as e:
                        print(f"⚠️ Failed to parse message: {e}")
                        continue

            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"⚠️ Error polling for pipeline progression: {e}")
            await asyncio.sleep(1)

    print(f"⏰ Pipeline did not complete within {timeout_seconds} seconds")
    return None
