"""Integration guard for BT SE batch quality metadata persistence.

Verifies that CJBatchState.processing_metadata can safely persist bt_se_summary
and bt_quality_flags via merge_batch_processing_metadata using real database
infrastructure and session provider.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from services.cj_assessment_service.cj_core_logic.batch_submission import (
    merge_batch_processing_metadata,
)
from services.cj_assessment_service.models_db import CJBatchState
from services.cj_assessment_service.tests.fixtures.database_fixtures import (
    PostgresDataAccess,
)


@pytest.mark.integration
async def test_bt_batch_quality_metadata_persisted_on_cj_batch_state(
    postgres_data_access: PostgresDataAccess,
) -> None:
    """Persist bt_se_summary and bt_quality_flags on CJBatchState.processing_metadata."""

    async with postgres_data_access.session() as session:
        # Create a minimal batch; expected_essay_count choice is not critical here.
        cj_batch = await postgres_data_access.create_new_cj_batch(
            session=session,
            bos_batch_id="bt-quality-metadata-test",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=None,
            expected_essay_count=4,
        )
        await session.commit()

    # Construct realistic diagnostic payloads
    bt_se_summary = {
        "mean_se": 0.15,
        "max_se": 0.3,
        "min_se": 0.1,
        "item_count": 4,
        "comparison_count": 3,
        "items_at_cap": 0,
        "isolated_items": 1,
        "mean_comparisons_per_item": 1.5,
        "min_comparisons_per_item": 0,
        "max_comparisons_per_item": 3,
    }
    bt_quality_flags = {
        "bt_se_inflated": False,
        "comparison_coverage_sparse": False,
        "has_isolated_items": True,
    }

    metadata_updates = {
        "bt_scores": {"essay-1": 0.1},
        "last_scored_iteration": 1,
        "last_score_change": 0.01,
        "bt_se_summary": bt_se_summary,
        "bt_quality_flags": bt_quality_flags,
    }

    # Persist metadata using the same helper used by workflow_continuation
    await merge_batch_processing_metadata(
        session_provider=postgres_data_access.session_provider,
        cj_batch_id=cj_batch.id,
        metadata_updates=metadata_updates,
        correlation_id=uuid4(),
    )

    # Reload CJBatchState and verify persisted metadata shape and JSON safety
    async with postgres_data_access.session() as session:
        result = await session.execute(
            select(CJBatchState.processing_metadata).where(CJBatchState.batch_id == cj_batch.id)
        )
        processing_metadata = result.scalar_one()

    assert isinstance(processing_metadata, dict)
    assert "bt_se_summary" in processing_metadata
    assert "bt_quality_flags" in processing_metadata

    persisted_se_summary = processing_metadata["bt_se_summary"]
    persisted_flags = processing_metadata["bt_quality_flags"]

    # Basic shape checks
    for key in bt_se_summary:
        assert key in persisted_se_summary
    assert set(persisted_flags.keys()) == {
        "bt_se_inflated",
        "comparison_coverage_sparse",
        "has_isolated_items",
    }

    # Ensure the metadata (including diagnostics) is JSON-serializable
    json.dumps(processing_metadata)
