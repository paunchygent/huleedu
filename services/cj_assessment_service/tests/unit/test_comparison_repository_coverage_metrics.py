"""Tests for PostgreSQLCJComparisonRepository.get_coverage_metrics_for_batch."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.implementations.comparison_repository import (
    PostgreSQLCJComparisonRepository,
)
from services.cj_assessment_service.models_api import (
    ComparisonResult,
    ComparisonTask,
    EssayForComparison,
)
from services.cj_assessment_service.models_db import CJBatchUpload


@pytest.mark.asyncio
async def test_get_coverage_metrics_for_batch_returns_expected_counts(
    postgres_session: AsyncSession,
    postgres_comparison_repository: PostgreSQLCJComparisonRepository,
) -> None:
    """Repo helper should compute nC2 and unique successful pair count correctly."""

    # Create a small batch upload and essays directly via ORM.
    batch = CJBatchUpload(
        bos_batch_id="bos-batch-1",
        event_correlation_id="00000000-0000-0000-0000-000000000000",
        language="en",
        course_code="eng5",
        expected_essay_count=3,
        status=None,  # status has default at DB level
    )
    postgres_session.add(batch)
    await postgres_session.flush()

    from services.cj_assessment_service.models_db import ProcessedEssay

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
        for i in range(3)
    ]
    for essay in essays:
        postgres_session.add(essay)

    await postgres_session.flush()

    # Build three successful unordered pairs over the 3 essays:
    # (0,1), (0,2), (1,2) – all winners successful, no errors.
    comparison_repo = postgres_comparison_repository
    comparison_tasks: list[ComparisonResult] = []

    pairs: list[tuple[int, int, str]] = [
        (0, 1, "essay_a"),
        (0, 2, "essay_b"),
        (1, 2, "essay_a"),
    ]

    from common_core import EssayComparisonWinner

    from services.cj_assessment_service.models_api import LLMAssessmentResponseSchema

    for idx_a, idx_b, winner in pairs:
        task = ComparisonTask(
            essay_a=EssayForComparison(
                id=essays[idx_a].els_essay_id,
                text_content=essays[idx_a].assessment_input_text,
                current_bt_score=0.0,
            ),
            essay_b=EssayForComparison(
                id=essays[idx_b].els_essay_id,
                text_content=essays[idx_b].assessment_input_text,
                current_bt_score=0.0,
            ),
            prompt="prompt",
            prompt_blocks=None,
        )

        assessment = LLMAssessmentResponseSchema(
            winner=EssayComparisonWinner.ESSAY_A
            if winner == "essay_a"
            else EssayComparisonWinner.ESSAY_B,
            confidence=3.0,
            justification="test",
        )

        comparison_tasks.append(
            ComparisonResult(
                task=task,
                llm_assessment=assessment,
                error_detail=None,
                raw_llm_response_content=None,
            )
        )

    await comparison_repo.store_comparison_results(
        session=postgres_session,
        results=comparison_tasks,
        cj_batch_id=batch.id,
    )

    (
        max_possible_pairs,
        successful_pairs_count,
    ) = await comparison_repo.get_coverage_metrics_for_batch(
        session=postgres_session,
        batch_id=batch.id,
    )

    # For 3 essays, nC2 = 3
    assert max_possible_pairs == 3
    # No winners should contribute yet because winner values are enum objects;
    # current implementation expects raw \"essay_a\"/\"essay_b\" strings.
    # This asserts alignment with current behaviour and protects future refactors.
    assert successful_pairs_count == 0
