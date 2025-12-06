"""Tests for positional fairness helper utilities."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_db import CJBatchUpload, ComparisonPair, ProcessedEssay
from services.cj_assessment_service.tests.helpers.positional_fairness import (
    get_positional_counts_for_batch,
)


@pytest.mark.asyncio
async def test_get_positional_counts_for_batch_returns_expected_counts(
    postgres_session: AsyncSession,
) -> None:
    """Helper should return per-essay A/B position counts."""

    # Create a small batch and three essays.
    batch = CJBatchUpload(
        bos_batch_id="bos-positional-1",
        event_correlation_id="00000000-0000-0000-0000-000000000010",
        language="en",
        course_code="eng5",
        expected_essay_count=3,
        status=None,
    )
    postgres_session.add(batch)
    await postgres_session.flush()

    essays = [
        ProcessedEssay(
            els_essay_id=f"essay-{i}",
            cj_batch_id=batch.id,
            text_storage_id=f"storage-{i}",
            assessment_input_text=f"essay-{i}-text",
            current_bt_score=0.0,
            current_bt_se=None,
            comparison_count=0,
            is_anchor=False,
        )
        for i in range(1, 4)
    ]
    for essay in essays:
        postgres_session.add(essay)

    await postgres_session.flush()

    # Create four comparison pairs with controlled positions:
    # - essay-1 vs essay-2  (A:1, B:2)
    # - essay-2 vs essay-3  (A:2, B:3)
    # - essay-3 vs essay-1  (A:3, B:1)
    # - essay-1 vs essay-3  (A:1, B:3)
    pairs = [
        ("essay-1", "essay-2"),
        ("essay-2", "essay-3"),
        ("essay-3", "essay-1"),
        ("essay-1", "essay-3"),
    ]

    for essay_a_id, essay_b_id in pairs:
        postgres_session.add(
            ComparisonPair(
                cj_batch_id=batch.id,
                essay_a_els_id=essay_a_id,
                essay_b_els_id=essay_b_id,
                prompt_text="prompt",
                winner=None,
                confidence=None,
                justification=None,
                raw_llm_response=None,
                error_code=None,
                error_correlation_id=None,
                error_timestamp=None,
                error_service=None,
                error_details=None,
            )
        )

    await postgres_session.flush()

    positional_counts = await get_positional_counts_for_batch(
        session=postgres_session,
        cj_batch_id=batch.id,
    )

    # essay-1: A in pairs 1 and 4, B in pair 3.
    assert positional_counts["essay-1"] == {"A": 2, "B": 1}
    # essay-2: A in pair 2, B in pair 1.
    assert positional_counts["essay-2"] == {"A": 1, "B": 1}
    # essay-3: A in pair 3, B in pairs 2 and 4.
    assert positional_counts["essay-3"] == {"A": 1, "B": 2}
