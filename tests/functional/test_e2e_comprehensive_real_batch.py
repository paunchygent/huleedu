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

import pytest

from tests.functional.client_pipeline_test_utils import publish_client_pipeline_request
from tests.functional.comprehensive_pipeline_utils import (
    create_comprehensive_kafka_manager,
    load_real_test_essays,
    register_comprehensive_batch,
    upload_real_essays,
    watch_pipeline_progression_with_consumer,
)
from tests.utils.auth_manager import AuthTestManager
from tests.utils.event_factory import reset_test_event_factory
from tests.utils.service_test_manager import ServiceTestManager


@pytest.mark.slow
@pytest.mark.e2e
@pytest.mark.functional
@pytest.mark.asyncio
@pytest.mark.timeout(240)  # 4 minute timeout for complete pipeline with mock LLM
async def test_comprehensive_real_batch_pipeline(verify_redis_is_pristine):
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

    The verify_redis_is_pristine fixture ensures clean Redis state before test.
    """
    # Diagnostic fixture ensures clean Redis state - just reference it
    _ = verify_redis_is_pristine

    # Initialize unique event factory for this test run
    event_factory = reset_test_event_factory()

    # Validate real test essays are available
    test_essays = await load_real_test_essays(max_essays=25)

    # Step 1: Initialize authentication and service manager
    auth_manager = AuthTestManager()
    service_manager = ServiceTestManager(auth_manager=auth_manager)
    test_teacher = auth_manager.create_teacher_user("Comprehensive Test Teacher")

    # Validate all services are healthy using modern utility
    endpoints = await service_manager.get_validated_endpoints()
    assert len(endpoints) >= 4, f"Expected at least 4 services, got {len(endpoints)}"
    print(f"✅ {len(endpoints)} services validated healthy")

    # Step 2: Set up Kafka manager for pipeline events FIRST (before any actions)
    kafka_manager = create_comprehensive_kafka_manager()
    print("✅ Kafka manager configured for comprehensive pipeline")

    # Step 3: Generate unique correlation ID using event factory
    test_correlation_id = str(event_factory.create_unique_correlation_id())
    print(f"🔍 Test correlation ID: {test_correlation_id}")

    # Step 4: Set up consumer FIRST before any actions (critical timing fix)
    print("🔧 Setting up pipeline event monitoring FIRST...")

    # Get the pipeline topics for monitoring
    from tests.functional.comprehensive_pipeline_utils import PIPELINE_TOPICS

    pipeline_topics = list(PIPELINE_TOPICS.values())

    # Use KafkaTestManager (modern framework) with raw bytes (production fidelity)
    async with kafka_manager.consumer("comprehensive_real_batch", pipeline_topics) as consumer:
        print("✅ Pipeline monitoring consumer ready and positioned")

        # Step 5: Register batch with BOS using modern utility
        print("📝 Registering batch with BOS to create essay slots...")
        batch_id, actual_correlation_id = await register_comprehensive_batch(
            service_manager,
            len(test_essays),
            test_correlation_id,
            test_teacher,  # Pass authenticated user
        )
        print(f"✅ Batch registered with BOS: {batch_id}")
        print(f"🔗 Monitoring events with correlation ID: {actual_correlation_id}")

        # Step 6: Upload files to trigger the pipeline using modern utility
        print("🚀 Uploading real student essays to trigger pipeline...")
        upload_response = await upload_real_essays(
            service_manager,
            batch_id,
            test_essays,
            actual_correlation_id,
            test_teacher,  # Pass authenticated user
        )
        print(f"✅ File upload successful: {upload_response}")

        # TIMING FIX: Wait for essays to be processed by ELS before requesting pipeline
        # The workflow is: Upload → File Processing → ELS processes and stores
        # essays → ELS BatchEssaysReady → BOS ready to orchestrate
        # We need to wait for ELS processing to complete before the client can
        # request pipeline execution
        print("⏳ Waiting for essays to be processed by ELS...")

        import asyncio

        batch_ready_received = False

        # Monitor for batch readiness event based on Phase 1 flow
        # GUEST batches (no class_id) use BatchContentProvisioningCompleted
        # REGULAR batches (with class_id) use BatchEssaysReady after student matching
        async for message in consumer:
            try:
                if hasattr(message, "value"):
                    import json

                    if isinstance(message.value, bytes):
                        raw_message = message.value.decode("utf-8")
                    else:
                        raw_message = message.value

                    envelope_data = json.loads(raw_message)
                    event_data = envelope_data.get("data", {})
                    event_correlation_id = envelope_data.get("correlation_id")

                    # Check for BatchContentProvisioningCompleted (Phase 1 GUEST batch flow)
                    if (
                        message.topic == "huleedu.batch.content.provisioning.completed.v1"
                        and event_correlation_id == actual_correlation_id
                        and event_data.get("batch_id") == batch_id
                    ):
                        ready_count = event_data.get("provisioned_count", 0)
                        print(
                            f"📨 BatchContentProvisioningCompleted received: {ready_count} essays "
                            "ready for processing (GUEST batch flow)",
                        )
                        batch_ready_received = True
                        break

                    # Also check for BatchEssaysReady (in case this is a REGULAR batch)
                    if (
                        message.topic == "huleedu.els.batch.essays.ready.v1"
                        and event_correlation_id == actual_correlation_id
                        and event_data.get("batch_id") == batch_id
                    ):
                        ready_count = len(event_data.get("ready_essays", []))
                        print(
                            f"📨 BatchEssaysReady received: {ready_count} essays "
                            "ready for processing (REGULAR batch flow)",
                        )
                        batch_ready_received = True
                        break

            except Exception as e:
                print(f"⚠️ Error waiting for batch ready: {e}")
                continue

        if not batch_ready_received:
            raise Exception(
                "Neither BatchContentProvisioningCompleted nor BatchEssaysReady event was received - "
                "essays may not be processed by ELS",
            )

        # Give BOS a moment to process the batch readiness event
        await asyncio.sleep(2)
        print("✅ Essays confirmed processed by ELS, BOS ready for client pipeline request")

        # ARCHITECTURAL FIX: Explicitly trigger pipeline execution via client request
        # Essays are now stored persistently and BOS is ready to process client requests
        # This follows the new client-controlled architecture
        request_correlation_id = await publish_client_pipeline_request(
            kafka_manager,
            batch_id,
            "cj_assessment",  # Use cj_assessment pipeline for comprehensive testing
            actual_correlation_id,
        )
        print(
            "📡 Published cj_assessment pipeline request with "
            f"correlation: {request_correlation_id}"
        )

        # Step 7: Watch pipeline progression with pre-positioned consumer
        print("⏳ Watching pipeline progression...")
        result = await watch_pipeline_progression_with_consumer(
            consumer,
            batch_id,
            request_correlation_id,
            len(test_essays),
            50,  # 50 seconds timeout for faster debugging
        )

        assert result is not None, "Pipeline did not complete"
        print(f"✅ Complete pipeline success! Pipeline completed with result: {result}")
