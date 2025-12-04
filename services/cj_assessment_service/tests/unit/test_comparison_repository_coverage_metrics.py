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
    """Repo helper should compute nC2 and successful pair count correctly.

    When there are 3 essays and 3 successful comparisons, max_possible_pairs
    should be 3 and successful_pairs_count should also be 3. Coverage logic
    treats any unordered pair with at least one non-error winner as
    "successful", regardless of whether the winner was stored as an enum or
    a raw string, and ignores only error-only pairs.
    """

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
    # All three unordered pairs have at least one non-error winner recorded.
    assert successful_pairs_count == 3


@pytest.mark.asyncio
async def test_coverage_ignores_error_only_pairs(
    postgres_session: AsyncSession,
    postgres_comparison_repository: PostgreSQLCJComparisonRepository,
) -> None:
    """Pairs that only ever see error results are not counted as successful."""

    batch = CJBatchUpload(
        bos_batch_id="bos-batch-errors",
        event_correlation_id="00000000-0000-0000-0000-000000000001",
        language="en",
        course_code="eng5",
        expected_essay_count=3,
        status=None,
    )
    postgres_session.add(batch)
    await postgres_session.flush()

    from services.cj_assessment_service.models_db import ComparisonPair, ProcessedEssay

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

    # Create three unordered pairs over the 3 essays:
    # (0,1) → error-only; (0,2) and (1,2) → successful.
    error_only_pair = ComparisonPair(
        cj_batch_id=batch.id,
        essay_a_els_id=essays[0].els_essay_id,
        essay_b_els_id=essays[1].els_essay_id,
        prompt_text="prompt",
        winner="error",
        confidence=None,
        justification=None,
        raw_llm_response=None,
        error_code="LLM_TIMEOUT",
        error_correlation_id=None,
        error_timestamp=None,
        error_service="llm_provider_service",
        error_details={"reason": "timeout"},
    )

    success_pairs = [
        ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id=essays[0].els_essay_id,
            essay_b_els_id=essays[2].els_essay_id,
            prompt_text="prompt",
            winner="essay_a",
            confidence=3.0,
            justification="A wins",
            raw_llm_response=None,
            error_code=None,
            error_correlation_id=None,
            error_timestamp=None,
            error_service=None,
            error_details=None,
        ),
        ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id=essays[1].els_essay_id,
            essay_b_els_id=essays[2].els_essay_id,
            prompt_text="prompt",
            winner="essay_b",
            confidence=3.0,
            justification="B wins",
            raw_llm_response=None,
            error_code=None,
            error_correlation_id=None,
            error_timestamp=None,
            error_service=None,
            error_details=None,
        ),
    ]

    postgres_session.add(error_only_pair)
    for pair in success_pairs:
        postgres_session.add(pair)

    await postgres_session.flush()

    (
        max_possible_pairs,
        successful_pairs_count,
    ) = await postgres_comparison_repository.get_coverage_metrics_for_batch(
        session=postgres_session,
        batch_id=batch.id,
    )

    # For 3 essays, nC2 = 3; only two unordered pairs ever see a non-error winner.
    assert max_possible_pairs == 3
    assert successful_pairs_count == 2


@pytest.mark.asyncio
async def test_coverage_counts_retry_success_after_error(
    postgres_session: AsyncSession,
    postgres_comparison_repository: PostgreSQLCJComparisonRepository,
) -> None:
    """Pairs that eventually succeed after an error should count as covered."""

    from unittest.mock import AsyncMock
    from uuid import uuid4

    from common_core.domain_enums import EssayComparisonWinner

    from services.cj_assessment_service.cj_core_logic.batch_completion_policy import (
        BatchCompletionPolicy,
    )
    from services.cj_assessment_service.cj_core_logic.batch_submission_tracking import (
        create_tracking_records,
    )
    from services.cj_assessment_service.cj_core_logic.callback_persistence_service import (
        CallbackPersistenceService,
    )
    from services.cj_assessment_service.cj_core_logic.callback_retry_coordinator import (
        ComparisonRetryCoordinator,
    )
    from services.cj_assessment_service.tests.unit.test_callback_state_manager import (
        create_llm_comparison_result,
    )

    batch = CJBatchUpload(
        bos_batch_id="bos-batch-retry",
        event_correlation_id="00000000-0000-0000-0000-000000000002",
        language="en",
        course_code="eng5",
        expected_essay_count=2,
        status=None,
    )
    postgres_session.add(batch)
    await postgres_session.flush()

    from services.cj_assessment_service.models_db import ComparisonPair, ProcessedEssay

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
        for i in range(2)
    ]
    for essay in essays:
        postgres_session.add(essay)

    await postgres_session.flush()

    # Create tracking record for a single pair via real helper.
    task = ComparisonTask(
        essay_a=EssayForComparison(
            id=essays[0].els_essay_id,
            text_content=essays[0].assessment_input_text,
            current_bt_score=0.0,
        ),
        essay_b=EssayForComparison(
            id=essays[1].els_essay_id,
            text_content=essays[1].assessment_input_text,
            current_bt_score=0.0,
        ),
        prompt="prompt",
        prompt_blocks=None,
    )

    correlation_id = uuid4()
    tracking_map = await create_tracking_records(
        session=postgres_session,
        batch_tasks=[task],
        cj_batch_id=batch.id,
        correlation_id=correlation_id,
    )

    request_correlation_id = next(iter(tracking_map.values()))

    # Load the created ComparisonPair and simulate an error followed by success
    # on the same tracking row.
    from sqlalchemy import select

    result = await postgres_session.execute(
        select(ComparisonPair).where(
            ComparisonPair.cj_batch_id == batch.id,
            ComparisonPair.request_correlation_id == request_correlation_id,
        )
    )
    comparison_pair = result.scalars().one()

    service = CallbackPersistenceService(
        completion_policy=AsyncMock(spec=BatchCompletionPolicy),
        retry_coordinator=AsyncMock(spec=ComparisonRetryCoordinator),
    )

    # First: error callback marks the pair as errored.
    error_result = create_llm_comparison_result(
        correlation_id=request_correlation_id,
        is_error=True,
    )
    service._apply_error_update(comparison_pair, error_result)

    # Then: a successful retry updates the winner but leaves error fields set.
    success_result = create_llm_comparison_result(
        correlation_id=request_correlation_id,
        is_error=False,
        winner=EssayComparisonWinner.ESSAY_A,
    )
    service._apply_success_update(comparison_pair, success_result)

    await postgres_session.flush()

    (
        max_possible_pairs,
        successful_pairs_count,
    ) = await postgres_comparison_repository.get_coverage_metrics_for_batch(
        session=postgres_session,
        batch_id=batch.id,
    )

    # Two essays → nC2 = 1; the pair should now count as successfully covered
    # despite retaining error metadata from the initial failure.
    assert max_possible_pairs == 1
    assert successful_pairs_count == 1
