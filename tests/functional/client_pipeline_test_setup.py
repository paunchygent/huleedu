"""
Client Pipeline Test Setup Utilities

Utility functions for setting up batches and essays for client pipeline E2E tests.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import List

from tests.functional.comprehensive_pipeline_utils import (
    load_real_test_essays,
    register_comprehensive_batch,
    upload_real_essays,
)
from tests.utils.service_test_manager import ServiceTestManager


async def create_test_batch_with_essays(
    service_manager: ServiceTestManager,
    essay_count: int = 3,
    correlation_id: str | None = None
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

    # Register batch for comprehensive testing
    batch_id = await register_comprehensive_batch(
        service_manager,
        expected_essay_count,
        correlation_id
    )
    print(f"📦 Created test batch: {batch_id}")

    # Upload essays to batch
    await upload_real_essays(
        service_manager,
        batch_id,
        essay_files,
        correlation_id
    )
    print(f"📚 Uploaded {expected_essay_count} essays")

    # Wait for batch to be ready
    await asyncio.sleep(5)

    return batch_id, correlation_id


async def create_multiple_test_batches(
    service_manager: ServiceTestManager,
    batch_count: int = 2,
    essays_per_batch: int = 2
) -> tuple[List[str], List[str]]:
    """
    Create multiple test batches for concurrent testing.

    Returns:
        Tuple of (batch_ids, correlation_ids)
    """
    batch_ids = []
    correlation_ids = []

    for i in range(batch_count):
        correlation_id = str(uuid.uuid4())
        correlation_ids.append(correlation_id)

        essay_files = await load_real_test_essays(max_essays=essays_per_batch)
        expected_essay_count = len(essay_files)

        batch_id = await register_comprehensive_batch(
            service_manager,
            expected_essay_count,
            correlation_id
        )
        batch_ids.append(batch_id)

        await upload_real_essays(
            service_manager,
            batch_id,
            essay_files,
            correlation_id
        )

        print(f"📦 Created test batch {i+1}: {batch_id}")

    # Wait for batches to be ready
    await asyncio.sleep(5)

    return batch_ids, correlation_ids


def get_pipeline_monitoring_topics() -> List[str]:
    """Get the standard list of topics for monitoring pipeline resolution."""
    return [
        "huleedu.commands.batch.pipeline.v1",
        "huleedu.els.spellcheck.initiate.command.v1",
        "huleedu.batch.ai_feedback.initiate.command.v1",
        "huleedu.batch.nlp.initiate.command.v1",
        "huleedu.batch.cj_assessment.initiate.command.v1",
        "huleedu.els.batch_phase.outcome.v1",
        "huleedu.events.batch.initiate_command.v1"
    ]


def get_state_aware_monitoring_topics() -> List[str]:
    """Get topics for state-aware pipeline monitoring."""
    return [
        "huleedu.commands.batch.pipeline.v1",
        "huleedu.els.spellcheck.initiate.command.v1",
        "huleedu.batch.ai_feedback.initiate.command.v1",
        "huleedu.batch.nlp.initiate.command.v1",
        "huleedu.batch.cj_assessment.initiate.command.v1",
        "huleedu.els.batch_phase.outcome.v1",
        "huleedu.events.batch.initiate_command.v1"
    ]


def get_concurrent_monitoring_topics() -> List[str]:
    """Get topics for concurrent pipeline monitoring."""
    return [
        "huleedu.commands.batch.pipeline.v1",
        "huleedu.els.spellcheck.initiate.command.v1",
        "huleedu.batch.ai_feedback.initiate.command.v1",
        "huleedu.batch.nlp.initiate.command.v1",
        "huleedu.batch.ai_feedback.initiate.command.v1",
        "huleedu.batch.nlp.initiate.command.v1",
        "huleedu.batch.cj_assessment.initiate.command.v1",
        "huleedu.els.batch_phase.outcome.v1"
    ]
