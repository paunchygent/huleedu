"""Tests for _fetch_per_pair_orientation_counts helper in pair_generation.

Validates AB/BA orientation counting semantics:
- AB count = times lower-ID essay was in A position
- BA count = times higher-ID essay was in A position (lower-ID in B)
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.pair_generation import (
    _fetch_per_pair_orientation_counts,
)
from services.cj_assessment_service.models_db import (
    CJBatchUpload,
    ComparisonPair,
    ProcessedEssay,
)


class TestFetchPerPairOrientationCounts:
    """Tests for _fetch_per_pair_orientation_counts helper."""

    @pytest.mark.asyncio
    async def test_mixed_orientations_returns_correct_ab_ba_counts(
        self,
        postgres_session: AsyncSession,
    ) -> None:
        """AB/BA counts match actual comparison pair orientations."""
        batch = CJBatchUpload(
            bos_batch_id="bos-orientation-mixed-1",
            event_correlation_id="00000000-0000-0000-0000-000000000020",
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

        # Create pairs with controlled orientations:
        # essay-1 vs essay-2: 2x AB (essay-1 in A), 1x BA (essay-2 in A)
        # essay-1 vs essay-3: 1x AB (essay-1 in A)
        # essay-2 vs essay-3: 1x BA (essay-3 in A)
        pair_orientations = [
            ("essay-1", "essay-2"),  # AB for (essay-1, essay-2)
            ("essay-1", "essay-2"),  # AB for (essay-1, essay-2)
            ("essay-2", "essay-1"),  # BA for (essay-1, essay-2)
            ("essay-1", "essay-3"),  # AB for (essay-1, essay-3)
            ("essay-3", "essay-2"),  # BA for (essay-2, essay-3)
        ]

        for essay_a_id, essay_b_id in pair_orientations:
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

        result = await _fetch_per_pair_orientation_counts(
            session=postgres_session,
            cj_batch_id=batch.id,
        )

        # (essay-1, essay-2): 2 AB, 1 BA
        assert result[("essay-1", "essay-2")] == (2, 1)
        # (essay-1, essay-3): 1 AB, 0 BA
        assert result[("essay-1", "essay-3")] == (1, 0)
        # (essay-2, essay-3): 0 AB, 1 BA (essay-3 was in A position)
        assert result[("essay-2", "essay-3")] == (0, 1)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "pairs,expected_key,expected_counts",
        [
            # Only AB orientation: lower-ID essay in A position
            ([("a", "b"), ("a", "b")], ("a", "b"), (2, 0)),
            # Only BA orientation: higher-ID essay in A position
            ([("b", "a"), ("b", "a")], ("a", "b"), (0, 2)),
            # Mixed AB and BA orientations
            ([("a", "b"), ("b", "a")], ("a", "b"), (1, 1)),
        ],
        ids=["only-ab", "only-ba", "mixed"],
    )
    async def test_single_pair_orientation_variants(
        self,
        postgres_session: AsyncSession,
        pairs: list[tuple[str, str]],
        expected_key: tuple[str, str],
        expected_counts: tuple[int, int],
    ) -> None:
        """Single pair with various orientation patterns."""
        batch = CJBatchUpload(
            bos_batch_id=f"bos-orientation-variant-{expected_counts}",
            event_correlation_id="00000000-0000-0000-0000-000000000021",
            language="en",
            course_code="eng5",
            expected_essay_count=2,
            status=None,
        )
        postgres_session.add(batch)
        await postgres_session.flush()

        for essay_id in ("a", "b"):
            postgres_session.add(
                ProcessedEssay(
                    els_essay_id=essay_id,
                    cj_batch_id=batch.id,
                    text_storage_id=f"storage-{essay_id}",
                    assessment_input_text=f"{essay_id}-text",
                    current_bt_score=0.0,
                    current_bt_se=None,
                    comparison_count=0,
                    is_anchor=False,
                )
            )
        await postgres_session.flush()

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

        result = await _fetch_per_pair_orientation_counts(
            session=postgres_session,
            cj_batch_id=batch.id,
        )

        assert result[expected_key] == expected_counts

    @pytest.mark.asyncio
    async def test_uuid_format_ids_normalized_correctly(
        self,
        postgres_session: AsyncSession,
    ) -> None:
        """UUID-format IDs are sorted and normalized to canonical key.

        Uses realistic UUIDs to verify string comparison handles
        UUID ordering correctly (lexicographic, not numeric).
        """
        batch = CJBatchUpload(
            bos_batch_id="bos-orientation-uuid-1",
            event_correlation_id="00000000-0000-0000-0000-000000000022",
            language="en",
            course_code="eng5",
            expected_essay_count=2,
            status=None,
        )
        postgres_session.add(batch)
        await postgres_session.flush()

        # UUIDs where lexicographic order differs from creation order
        uuid_low = "11111111-1111-1111-1111-111111111111"
        uuid_high = "ffffffff-ffff-ffff-ffff-ffffffffffff"

        for essay_id in (uuid_low, uuid_high):
            postgres_session.add(
                ProcessedEssay(
                    els_essay_id=essay_id,
                    cj_batch_id=batch.id,
                    text_storage_id=f"storage-{essay_id[:8]}",
                    assessment_input_text=f"{essay_id[:8]}-text",
                    current_bt_score=0.0,
                    current_bt_se=None,
                    comparison_count=0,
                    is_anchor=False,
                )
            )
        await postgres_session.flush()

        # Insert with higher UUID in A position (BA orientation)
        postgres_session.add(
            ComparisonPair(
                cj_batch_id=batch.id,
                essay_a_els_id=uuid_high,
                essay_b_els_id=uuid_low,
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

        result = await _fetch_per_pair_orientation_counts(
            session=postgres_session,
            cj_batch_id=batch.id,
        )

        # Key should be normalized to (uuid_low, uuid_high)
        # Count should be (0, 1) since uuid_high was in A position (BA orientation)
        expected_key = (uuid_low, uuid_high)
        assert expected_key in result
        assert result[expected_key] == (0, 1)

    @pytest.mark.asyncio
    async def test_empty_batch_returns_empty_dict(
        self,
        postgres_session: AsyncSession,
    ) -> None:
        """Batch with no comparison pairs returns empty dict."""
        batch = CJBatchUpload(
            bos_batch_id="bos-orientation-empty-1",
            event_correlation_id="00000000-0000-0000-0000-000000000023",
            language="en",
            course_code="eng5",
            expected_essay_count=2,
            status=None,
        )
        postgres_session.add(batch)
        await postgres_session.flush()

        result = await _fetch_per_pair_orientation_counts(
            session=postgres_session,
            cj_batch_id=batch.id,
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_multiple_pairs_same_essays_accumulated(
        self,
        postgres_session: AsyncSession,
    ) -> None:
        """Multiple comparisons of same pair accumulate counts correctly."""
        batch = CJBatchUpload(
            bos_batch_id="bos-orientation-accum-1",
            event_correlation_id="00000000-0000-0000-0000-000000000024",
            language="en",
            course_code="eng5",
            expected_essay_count=2,
            status=None,
        )
        postgres_session.add(batch)
        await postgres_session.flush()

        for essay_id in ("x", "y"):
            postgres_session.add(
                ProcessedEssay(
                    els_essay_id=essay_id,
                    cj_batch_id=batch.id,
                    text_storage_id=f"storage-{essay_id}",
                    assessment_input_text=f"{essay_id}-text",
                    current_bt_score=0.0,
                    current_bt_se=None,
                    comparison_count=0,
                    is_anchor=False,
                )
            )
        await postgres_session.flush()

        # 3 comparisons in AB orientation, 2 in BA orientation
        orientations = [
            ("x", "y"),  # AB
            ("x", "y"),  # AB
            ("x", "y"),  # AB
            ("y", "x"),  # BA
            ("y", "x"),  # BA
        ]

        for essay_a_id, essay_b_id in orientations:
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

        result = await _fetch_per_pair_orientation_counts(
            session=postgres_session,
            cj_batch_id=batch.id,
        )

        assert result[("x", "y")] == (3, 2)
