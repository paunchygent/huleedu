"""
Client Pipeline Test Setup Utilities

Utility functions for setting up batches and essays for client pipeline E2E tests.
"""

from __future__ import annotations

import asyncio
import uuid

from tests.functional.comprehensive_pipeline_utils import (
    load_real_test_essays,
    register_comprehensive_batch,
    upload_real_essays,
)
from tests.utils.service_test_manager import ServiceTestManager


async def create_test_batch_with_essays(
    service_manager: ServiceTestManager,
    essay_count: int = 3,
    correlation_id: str | None = None,
    test_teacher=None,
) -> tuple[str, str]:
    """
    Create a test batch with real essays for pipeline testing.

    Returns:
        Tuple of (batch_id, correlation_id)
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    # Load test essays
    essay_files = await load_real_test_essays(max_essays=essay_count)
    expected_essay_count = len(essay_files)

    # CRITICAL: Create consumer FIRST before any batch operations
    # This ensures the consumer is positioned and ready to receive batch readiness events
    from tests.functional.comprehensive_pipeline_utils import create_comprehensive_kafka_manager

    kafka_manager = create_comprehensive_kafka_manager()
    batch_ready_received = False
    batch_id = None

    # Monitor for batch readiness events (Phase 1 flow)
    async with kafka_manager.consumer(
        "batch_ready_wait",
        [
            "huleedu.els.batch.essays.ready.v1",
            "huleedu.batch.content.provisioning.completed.v1",  # Phase 1 GUEST batch event
        ],
    ) as consumer:
        print("⏳ Consumer positioned and ready to receive batch readiness events...")

        # Register batch for comprehensive testing
        batch_id, correlation_id = await register_comprehensive_batch(
            service_manager,
            expected_essay_count,
            correlation_id,
            test_teacher,
        )
        print(f"📦 Created test batch: {batch_id}")

        # Upload essays to batch
        await upload_real_essays(
            service_manager, batch_id, essay_files, correlation_id, test_teacher
        )
        print(f"📚 Uploaded {expected_essay_count} essays")

        print("⏳ Waiting for ELS to process essays (batch readiness event)...")

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
                        and event_correlation_id == correlation_id
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
                        and event_correlation_id == correlation_id
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
        raise RuntimeError(
            "Neither BatchContentProvisioningCompleted nor BatchEssaysReady event was received - "
            "essays may not be processed by ELS",
        )

    # Give BOS a moment to process the batch readiness event
    await asyncio.sleep(2)
    print("✅ Essays confirmed processed by ELS and ready for pipeline requests")

    return batch_id, correlation_id


async def create_multiple_test_batches(
    service_manager: ServiceTestManager,
    batch_count: int = 2,
    essays_per_batch: int = 2,
    test_teacher=None,
) -> tuple[list[str], list[str]]:
    """
    Create multiple test batches for concurrent testing.

    Returns:
        Tuple of (batch_ids, correlation_ids)
    """
    batch_ids = []
    correlation_ids = []

    for i in range(batch_count):
        # Generate a correlation ID for the initial request
        request_correlation_id = str(uuid.uuid4())

        essay_files = await load_real_test_essays(max_essays=essays_per_batch)
        expected_essay_count = len(essay_files)

        # The service returns the actual correlation ID used for the event stream
        batch_id, event_correlation_id = await register_comprehensive_batch(
            service_manager,
            expected_essay_count,
            request_correlation_id,
            test_teacher,
        )
        batch_ids.append(batch_id)
        # We must use the correlation ID from the service for monitoring
        correlation_ids.append(event_correlation_id)

        await upload_real_essays(
            service_manager, batch_id, essay_files, event_correlation_id, test_teacher
        )

        print(f"📦 Created test batch {i + 1}: {batch_id}")

    # Wait for batches to be ready
    await asyncio.sleep(5)

    return batch_ids, correlation_ids


def get_pipeline_monitoring_topics() -> list[str]:
    """Get the standard list of topics for monitoring pipeline resolution."""
    return [
        "huleedu.commands.batch.pipeline.v1",
        "huleedu.els.spellcheck.initiate.command.v1",
        "huleedu.batch.ai_feedback.initiate.command.v1",
        "huleedu.batch.nlp.initiate.command.v2",
        "huleedu.batch.cj_assessment.initiate.command.v1",
        "huleedu.els.batch.phase.outcome.v1",
        "huleedu.events.batch.initiate_command.v1",
    ]


def get_state_aware_monitoring_topics() -> list[str]:
    """Get topics for state-aware pipeline monitoring."""
    return [
        "huleedu.commands.batch.pipeline.v1",
        "huleedu.els.spellcheck.initiate.command.v1",
        "huleedu.batch.ai_feedback.initiate.command.v1",
        "huleedu.batch.nlp.initiate.command.v2",
        "huleedu.batch.cj_assessment.initiate.command.v1",
        "huleedu.els.batch.phase.outcome.v1",
        "huleedu.events.batch.initiate_command.v1",
    ]


def get_concurrent_monitoring_topics() -> list[str]:
    """Get topics for concurrent pipeline monitoring."""
    # Use set to ensure uniqueness
    return list(
        set(
            [
                "huleedu.commands.batch.pipeline.v1",
                "huleedu.els.spellcheck.initiate.command.v1",
                "huleedu.batch.ai_feedback.initiate.command.v1",
                "huleedu.batch.nlp.initiate.command.v2",
                "huleedu.batch.cj_assessment.initiate.command.v1",
                "huleedu.els.batch.phase.outcome.v1",
            ]
        )
    )
