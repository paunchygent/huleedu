"""Tests for positional fairness helper utilities."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_db import CJBatchUpload, ComparisonPair, ProcessedEssay
from services.cj_assessment_service.tests.helpers.positional_fairness import (
    get_pair_orientation_counts_for_batch,
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


@pytest.mark.asyncio
async def test_get_pair_orientation_counts_for_batch_returns_expected_counts(
    postgres_session: AsyncSession,
) -> None:
    """Helper should return per-pair AB/BA orientation counts.

    Canonical key format: (min_essay_id, max_essay_id)
    - AB_count = times min_id appeared in A position
    - BA_count = times min_id appeared in B position
    """
    batch = CJBatchUpload(
        bos_batch_id="bos-orientation-1",
        event_correlation_id="00000000-0000-0000-0000-000000000011",
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
            text_storage_id=f"storage-orient-{i}",
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

    # Create pairs with controlled orientations:
    # - (essay-1, essay-2): AB orientation
    # - (essay-2, essay-1): BA orientation (same canonical pair)
    # - (essay-1, essay-3): AB orientation
    # - (essay-3, essay-1): BA orientation (same canonical pair)
    # - (essay-2, essay-3): AB orientation only
    pairs = [
        ("essay-1", "essay-2"),  # (1,2) AB
        ("essay-2", "essay-1"),  # (1,2) BA
        ("essay-1", "essay-3"),  # (1,3) AB
        ("essay-3", "essay-1"),  # (1,3) BA
        ("essay-2", "essay-3"),  # (2,3) AB only
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

    pair_counts = await get_pair_orientation_counts_for_batch(
        session=postgres_session,
        cj_batch_id=batch.id,
    )

    # (essay-1, essay-2): 1 AB + 1 BA
    assert pair_counts[("essay-1", "essay-2")] == (1, 1)

    # (essay-1, essay-3): 1 AB + 1 BA
    assert pair_counts[("essay-1", "essay-3")] == (1, 1)

    # (essay-2, essay-3): 1 AB + 0 BA (missing complement)
    assert pair_counts[("essay-2", "essay-3")] == (1, 0)


@pytest.mark.asyncio
async def test_get_positional_counts_for_batch_filters_by_mode(
    postgres_session: AsyncSession,
) -> None:
    """Helper should filter by pair_generation_mode when specified."""

    batch = CJBatchUpload(
        bos_batch_id="bos-mode-filter-1",
        event_correlation_id="00000000-0000-0000-0000-000000000012",
        language="en",
        course_code="eng5",
        expected_essay_count=3,
        status=None,
    )
    postgres_session.add(batch)
    await postgres_session.flush()

    essays = [
        ProcessedEssay(
            els_essay_id=f"essay-mode-{i}",
            cj_batch_id=batch.id,
            text_storage_id=f"storage-mode-{i}",
            assessment_input_text=f"essay-mode-{i}-text",
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

    # Create pairs with different modes:
    # - 2 coverage pairs
    # - 2 resampling pairs
    postgres_session.add(
        ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id="essay-mode-1",
            essay_b_els_id="essay-mode-2",
            prompt_text="prompt",
            pair_generation_mode="coverage",
        )
    )
    postgres_session.add(
        ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id="essay-mode-2",
            essay_b_els_id="essay-mode-3",
            prompt_text="prompt",
            pair_generation_mode="coverage",
        )
    )
    postgres_session.add(
        ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id="essay-mode-1",
            essay_b_els_id="essay-mode-3",
            prompt_text="prompt",
            pair_generation_mode="resampling",
        )
    )
    postgres_session.add(
        ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id="essay-mode-3",
            essay_b_els_id="essay-mode-1",
            prompt_text="prompt",
            pair_generation_mode="resampling",
        )
    )
    await postgres_session.flush()

    # Without mode filter: all pairs
    all_counts = await get_positional_counts_for_batch(
        session=postgres_session,
        cj_batch_id=batch.id,
    )
    assert all_counts["essay-mode-1"] == {"A": 2, "B": 1}
    assert all_counts["essay-mode-2"] == {"A": 1, "B": 1}
    assert all_counts["essay-mode-3"] == {"A": 1, "B": 2}

    # With coverage filter: only first 2 pairs
    coverage_counts = await get_positional_counts_for_batch(
        session=postgres_session,
        cj_batch_id=batch.id,
        mode="coverage",
    )
    assert coverage_counts["essay-mode-1"] == {"A": 1, "B": 0}
    assert coverage_counts["essay-mode-2"] == {"A": 1, "B": 1}
    assert coverage_counts["essay-mode-3"] == {"A": 0, "B": 1}

    # With resampling filter: only last 2 pairs
    resampling_counts = await get_positional_counts_for_batch(
        session=postgres_session,
        cj_batch_id=batch.id,
        mode="resampling",
    )
    assert resampling_counts["essay-mode-1"] == {"A": 1, "B": 1}
    assert resampling_counts["essay-mode-3"] == {"A": 1, "B": 1}
    # essay-mode-2 not in resampling pairs
    assert "essay-mode-2" not in resampling_counts


@pytest.mark.asyncio
async def test_get_pair_orientation_counts_for_batch_filters_by_mode(
    postgres_session: AsyncSession,
) -> None:
    """Helper should filter per-pair orientation counts by mode."""

    batch = CJBatchUpload(
        bos_batch_id="bos-orient-mode-1",
        event_correlation_id="00000000-0000-0000-0000-000000000013",
        language="en",
        course_code="eng5",
        expected_essay_count=2,
        status=None,
    )
    postgres_session.add(batch)
    await postgres_session.flush()

    essays = [
        ProcessedEssay(
            els_essay_id=f"essay-orient-{i}",
            cj_batch_id=batch.id,
            text_storage_id=f"storage-orient-mode-{i}",
            assessment_input_text=f"essay-orient-{i}-text",
            current_bt_score=0.0,
            current_bt_se=None,
            comparison_count=0,
            is_anchor=False,
        )
        for i in range(1, 3)
    ]
    for essay in essays:
        postgres_session.add(essay)
    await postgres_session.flush()

    # Same pair (essay-orient-1, essay-orient-2) in different orientations and modes:
    # Coverage: AB orientation
    postgres_session.add(
        ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id="essay-orient-1",
            essay_b_els_id="essay-orient-2",
            prompt_text="prompt",
            pair_generation_mode="coverage",
        )
    )
    # Resampling: BA orientation (essay-2 in A, essay-1 in B)
    postgres_session.add(
        ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id="essay-orient-2",
            essay_b_els_id="essay-orient-1",
            prompt_text="prompt",
            pair_generation_mode="resampling",
        )
    )
    await postgres_session.flush()

    # Without mode filter: 1 AB + 1 BA
    all_orientations = await get_pair_orientation_counts_for_batch(
        session=postgres_session,
        cj_batch_id=batch.id,
    )
    assert all_orientations[("essay-orient-1", "essay-orient-2")] == (1, 1)

    # Coverage filter: only AB
    coverage_orientations = await get_pair_orientation_counts_for_batch(
        session=postgres_session,
        cj_batch_id=batch.id,
        mode="coverage",
    )
    assert coverage_orientations[("essay-orient-1", "essay-orient-2")] == (1, 0)

    # Resampling filter: only BA
    resampling_orientations = await get_pair_orientation_counts_for_batch(
        session=postgres_session,
        cj_batch_id=batch.id,
        mode="resampling",
    )
    assert resampling_orientations[("essay-orient-1", "essay-orient-2")] == (0, 1)
