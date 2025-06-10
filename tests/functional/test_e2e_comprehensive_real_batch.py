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

import uuid

import pytest

from tests.functional.comprehensive_pipeline_utils import (
    create_comprehensive_kafka_manager,
    load_real_test_essays,
    register_comprehensive_batch,
    upload_real_essays,
    watch_pipeline_progression_with_consumer,
)
from tests.utils.service_test_manager import ServiceTestManager


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
    test_essays = await load_real_test_essays(max_essays=25)

    # Step 1: Validate all services are healthy using modern utility
    service_manager = ServiceTestManager()
    endpoints = await service_manager.get_validated_endpoints()
    assert len(endpoints) >= 4, f"Expected at least 4 services, got {len(endpoints)}"
    print(f"✅ {len(endpoints)} services validated healthy")

    # Step 2: Set up Kafka manager for pipeline events FIRST (before any actions)
    kafka_manager = create_comprehensive_kafka_manager()
    print("✅ Kafka manager configured for comprehensive pipeline")

    # Step 3: Generate a valid UUID for the correlation ID
    test_correlation_id = str(uuid.uuid4())
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
        batch_id = await register_comprehensive_batch(
            service_manager, len(test_essays), test_correlation_id
        )
        print(f"✅ Batch registered with BOS: {batch_id}")

        # Step 6: Upload files to trigger the pipeline using modern utility
        print("🚀 Uploading real student essays to trigger pipeline...")
        upload_response = await upload_real_essays(
            service_manager, batch_id, test_essays, test_correlation_id
        )
        print(f"✅ File upload successful: {upload_response}")

        # Step 7: Watch pipeline progression with pre-positioned consumer
        print("⏳ Watching pipeline progression...")
        result = await watch_pipeline_progression_with_consumer(
            consumer, batch_id, test_correlation_id, len(test_essays), 50
        )

        assert result is not None, "Pipeline did not complete"
        print(f"✅ Complete pipeline success! Pipeline completed with result: {result}")
