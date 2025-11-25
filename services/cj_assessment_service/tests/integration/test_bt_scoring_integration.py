"""Integration tests for Bradley-Terry scoring and ranking system.

This module tests the core scoring algorithm including:
- Bradley-Terry score computation via choix
- Standard error calculation via Fisher Information
- Incremental score updates as comparisons arrive
- Score stability and convergence
- Database persistence of scores
- Edge cases and error handling

Tests use real database and realistic comparison data.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING
from uuid import uuid4

import numpy as np
import pytest
from common_core import EssayComparisonWinner
from sqlalchemy import select

from services.cj_assessment_service.cj_core_logic.bt_inference import (
    estimate_required_comparisons,
)
from services.cj_assessment_service.cj_core_logic.scoring_ranking import (
    check_score_stability,
    get_essay_rankings,
    record_comparisons_and_update_scores,
)
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import (
    ComparisonResult,
    ComparisonTask,
    EssayForComparison,
    LLMAssessmentResponseSchema,
)
from services.cj_assessment_service.models_db import (
    ProcessedEssay,
)
from services.cj_assessment_service.tests.fixtures.database_fixtures import (
    PostgresDataAccess,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.protocols import (
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    SessionProviderProtocol,
)


@pytest.mark.integration
class TestBradleyTerryScoring:
    """Test Bradley-Terry scoring system with real database."""

    async def _create_test_batch(
        self,
        data_access: PostgresDataAccess,
        session: AsyncSession,
        essay_count: int,
        batch_id: str = "test-batch",
    ) -> tuple[int, list[EssayForComparison]]:
        """Create a test batch with essays."""
        # Create batch
        cj_batch = await data_access.create_new_cj_batch(
            session=session,
            bos_batch_id=batch_id,
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=essay_count,
        )
        cj_batch.processing_metadata = {"student_prompt_text": "Test instructions"}

        # Create essays
        essays: list[EssayForComparison] = []
        for i in range(essay_count):
            essay_id = f"essay_{i}"
            await data_access.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=cj_batch.id,
                els_essay_id=essay_id,
                text_storage_id=f"storage_{i}",
                assessment_input_text=f"Essay content {i}",
            )
            essays.append(
                EssayForComparison(
                    id=essay_id,
                    text_content=f"Essay content {i}",
                    current_bt_score=None,
                )
            )

        await session.commit()  # Commit so batch data is visible to other sessions
        return cj_batch.id, essays

    def _create_comparison_results(
        self,
        essays: list[EssayForComparison],
        comparison_pattern: list[tuple[int, int, str]],
    ) -> list[ComparisonResult]:
        """Create comparison results based on pattern."""
        results = []
        for idx_a, idx_b, winner in comparison_pattern:
            essay_a = essays[idx_a]
            essay_b = essays[idx_b]

            if winner == "a":
                winner_enum = EssayComparisonWinner.ESSAY_A
            elif winner == "b":
                winner_enum = EssayComparisonWinner.ESSAY_B
            else:
                winner_enum = EssayComparisonWinner.ERROR

            task = ComparisonTask(
                essay_a=essay_a,
                essay_b=essay_b,
                prompt="Compare these essays",
            )

            assessment = LLMAssessmentResponseSchema(
                winner=winner_enum,
                justification=f"Essay {winner} is better",
                confidence=4.0,
            )

            results.append(
                ComparisonResult(
                    task=task,
                    llm_assessment=assessment,
                    raw_llm_response_content="Mock LLM response",
                )
            )
        return results

    async def test_basic_bt_score_computation(
        self,
        postgres_data_access: PostgresDataAccess,
        postgres_session: AsyncSession,
        postgres_session_provider: SessionProviderProtocol,
        postgres_comparison_repository: CJComparisonRepositoryProtocol,
        postgres_essay_repository: CJEssayRepositoryProtocol,
    ) -> None:
        """Test basic Bradley-Terry score computation with clear winner hierarchy."""
        # Create batch with 4 essays
        batch_id, essays = await self._create_test_batch(
            postgres_data_access,
            postgres_session,
            4,
        )

        # Create clear hierarchy: 0 > 1 > 2 > 3
        comparisons = [
            (0, 1, "a"),  # 0 beats 1
            (0, 2, "a"),  # 0 beats 2
            (0, 3, "a"),  # 0 beats 3
            (1, 2, "a"),  # 1 beats 2
            (1, 3, "a"),  # 1 beats 3
            (2, 3, "a"),  # 2 beats 3
        ]

        results = self._create_comparison_results(essays, comparisons)

        # Compute scores
        scores = await record_comparisons_and_update_scores(
            all_essays=essays,
            comparison_results=results,
            session_provider=postgres_session_provider,
            comparison_repository=postgres_comparison_repository,
            essay_repository=postgres_essay_repository,
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
        )

        # Validate score properties
        assert len(scores) == 4

        # Scores should be mean-centered
        mean_score = sum(scores.values()) / len(scores)
        assert abs(mean_score) < 1e-10, f"Scores not mean-centered: mean={mean_score}"

        # Verify ordering matches win pattern
        score_list = [(essay_id, score) for essay_id, score in scores.items()]
        score_list.sort(key=lambda x: x[1], reverse=True)

        assert score_list[0][0] == "essay_0", "Highest scorer should be essay_0"
        assert score_list[1][0] == "essay_1", "Second should be essay_1"
        assert score_list[2][0] == "essay_2", "Third should be essay_2"
        assert score_list[3][0] == "essay_3", "Lowest should be essay_3"

        # Verify scores decrease monotonically
        for i in range(len(score_list) - 1):
            assert score_list[i][1] > score_list[i + 1][1], "Scores should decrease"

    async def test_incremental_score_evolution(
        self,
        postgres_data_access: PostgresDataAccess,
        postgres_session: AsyncSession,
        postgres_session_provider: SessionProviderProtocol,
        postgres_comparison_repository: CJComparisonRepositoryProtocol,
        postgres_essay_repository: CJEssayRepositoryProtocol,
    ) -> None:
        """Test how scores evolve as comparisons arrive incrementally."""
        # Create batch with 6 essays
        batch_id, essays = await self._create_test_batch(
            postgres_data_access,
            postgres_session,
            6,
        )

        # Define all comparisons (15 total for complete graph)
        all_comparisons = [
            (0, 1, "a"),
            (0, 2, "a"),
            (0, 3, "a"),
            (0, 4, "a"),
            (0, 5, "a"),  # 0 wins all
            (1, 2, "a"),
            (1, 3, "a"),
            (1, 4, "b"),
            (1, 5, "b"),  # 1 mixed
            (2, 3, "a"),
            (2, 4, "b"),
            (2, 5, "b"),  # 2 mixed
            (3, 4, "b"),
            (3, 5, "b"),  # 3 loses most
            (4, 5, "a"),  # 4 beats 5
        ]

        # Process in increments: 20%, 40%, 60%, 80%, 100%
        increments = [3, 6, 9, 12, 15]
        previous_scores: dict[str, float] = {}
        stability_values: list[float] = []

        for increment in increments:
            partial_comparisons = all_comparisons[:increment]
            results = self._create_comparison_results(essays, partial_comparisons)

            scores = await record_comparisons_and_update_scores(
                all_essays=essays,
                comparison_results=results,
                session_provider=postgres_session_provider,
                comparison_repository=postgres_comparison_repository,
                essay_repository=postgres_essay_repository,
                cj_batch_id=batch_id,
                correlation_id=uuid4(),
            )

            # Check stability if we have previous scores
            if previous_scores:
                stability = check_score_stability(scores, previous_scores)
                stability_values.append(stability)

                # Scores should generally stabilize (decrease in change)
                assert stability >= 0, "Stability should be non-negative"

            previous_scores = scores.copy()

        # Verify stability improves (later values should be smaller)
        if len(stability_values) > 1:
            # Allow some noise but general trend should be decreasing
            avg_early = sum(stability_values[: len(stability_values) // 2]) / (
                len(stability_values) // 2
            )
            avg_late = sum(stability_values[len(stability_values) // 2 :]) / (
                len(stability_values) - len(stability_values) // 2
            )
            assert avg_late <= avg_early * 1.5, "Stability should generally improve"

    async def test_bt_standard_errors(
        self,
        postgres_data_access: PostgresDataAccess,
        postgres_session: AsyncSession,
        postgres_session_provider: SessionProviderProtocol,
        postgres_comparison_repository: CJComparisonRepositoryProtocol,
        postgres_essay_repository: CJEssayRepositoryProtocol,
    ) -> None:
        """Test analytical standard error computation."""
        # Create batch with 5 essays
        batch_id, essays = await self._create_test_batch(
            postgres_data_access,
            postgres_session,
            5,
        )

        # Create comparisons with varying density
        comparisons = [
            (0, 1, "a"),
            (0, 2, "a"),
            (0, 3, "a"),
            (0, 4, "a"),  # Essay 0: 4 comparisons
            (1, 2, "b"),
            (1, 3, "a"),  # Essay 1: 3 comparisons
            (2, 3, "b"),  # Essay 2: 3 comparisons
            # Essay 3: 4 comparisons
            # Essay 4: 1 comparison (sparse)
        ]

        results = self._create_comparison_results(essays, comparisons)

        # Compute scores
        await record_comparisons_and_update_scores(
            all_essays=essays,
            comparison_results=results,
            session_provider=postgres_session_provider,
            comparison_repository=postgres_comparison_repository,
            essay_repository=postgres_essay_repository,
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
        )

        # Use a fresh session to see the committed updates from record_comparisons_and_update_scores
        async with postgres_session_provider.session() as fresh_session:
            stmt = select(ProcessedEssay).where(ProcessedEssay.cj_batch_id == batch_id)
            result = await fresh_session.execute(stmt)
            db_essays = result.scalars().all()

            # Validate SE properties
            for essay in db_essays:
                assert essay.current_bt_se is not None, f"SE missing for {essay.els_essay_id}"
                assert essay.current_bt_se >= 0, "SE must be non-negative"
                assert essay.current_bt_se <= 2.0, "SE capped at 2.0"

                # Essay 4 is used as reference (SE=0) by choix/BT inference
                # So skip this check for essay_4
                if essay.comparison_count == 1 and essay.els_essay_id != "essay_4":
                    assert essay.current_bt_se > 0.1, (
                        f"Sparse essays should have higher SE: {essay.els_essay_id}"
                    )

    async def test_score_stability_checking(self) -> None:
        """Test score stability convergence checking."""
        # Test with identical scores (perfect stability)
        scores1 = {"essay_0": 0.5, "essay_1": -0.5}
        scores2 = {"essay_0": 0.5, "essay_1": -0.5}
        stability = check_score_stability(scores1, scores2)
        assert stability == 0.0, "Identical scores should have 0 stability change"

        # Test with small changes (stable)
        scores3 = {"essay_0": 0.52, "essay_1": -0.52}
        stability = check_score_stability(scores3, scores1)
        assert abs(stability - 0.02) < 1e-10, "Should detect small change"

        # Test with large changes (unstable)
        scores4 = {"essay_0": 1.5, "essay_1": -1.5}
        stability = check_score_stability(scores4, scores1)
        assert stability == 1.0, "Should detect large change"

        # Test with no previous scores
        stability = check_score_stability(scores1, {})
        assert math.isinf(stability), "No previous scores should return inf"

    @pytest.mark.parametrize(
        "scenario,essay_count,comparisons,should_raise",
        [
            # Single essay - should handle gracefully
            ("single_essay", 1, [], True),
            # No comparisons - should raise error
            ("no_comparisons", 3, [], True),
            # All ties/errors - should raise (no valid comparisons)
            ("all_errors", 3, [(0, 1, "error"), (1, 2, "error")], True),
            # Disconnected graph - should still work
            ("disconnected", 4, [(0, 1, "a"), (2, 3, "a")], False),
            # Extreme winner - one essay wins all
            ("extreme_winner", 4, [(0, 1, "a"), (0, 2, "a"), (0, 3, "a")], False),
            # Circular preferences A>B>C>A
            ("circular", 3, [(0, 1, "a"), (1, 2, "a"), (2, 0, "a")], False),
        ],
    )
    async def test_edge_cases(
        self,
        postgres_data_access: PostgresDataAccess,
        postgres_session: AsyncSession,
        postgres_session_provider: SessionProviderProtocol,
        postgres_comparison_repository: CJComparisonRepositoryProtocol,
        postgres_essay_repository: CJEssayRepositoryProtocol,
        scenario: str,
        essay_count: int,
        comparisons: list[tuple[int, int, str]],
        should_raise: bool,
    ) -> None:
        """Test Bradley-Terry scoring with edge cases."""
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        # Create batch and essays
        batch_id, essays = await self._create_test_batch(
            postgres_data_access,
            postgres_session,
            essay_count,
        )

        results = self._create_comparison_results(essays, comparisons)

        if should_raise:
            with pytest.raises(HuleEduError):
                await record_comparisons_and_update_scores(
                    all_essays=essays,
                    comparison_results=results,
                    session_provider=postgres_session_provider,
                    comparison_repository=postgres_comparison_repository,
                    essay_repository=postgres_essay_repository,
                    cj_batch_id=batch_id,
                    correlation_id=uuid4(),
                )
        else:
            scores = await record_comparisons_and_update_scores(
                all_essays=essays,
                comparison_results=results,
                session_provider=postgres_session_provider,
                comparison_repository=postgres_comparison_repository,
                essay_repository=postgres_essay_repository,
                cj_batch_id=batch_id,
                correlation_id=uuid4(),
            )

            # Basic validation
            assert len(scores) == essay_count
            mean_score = sum(scores.values()) / len(scores) if scores else 0
            assert abs(mean_score) < 1e-9, f"Not mean-centered: {mean_score}"

            # Scenario-specific validations
            if scenario == "extreme_winner":
                # Essay 0 should have highest score
                assert scores["essay_0"] == max(scores.values())
            elif scenario == "circular":
                # Scores should be relatively close due to regularization
                score_vals = list(scores.values())
                score_range = max(score_vals) - min(score_vals)
                assert score_range < 2.0, "Circular should have bounded range"

    async def test_database_persistence(
        self,
        postgres_data_access: PostgresDataAccess,
        postgres_session: AsyncSession,
        postgres_session_provider: SessionProviderProtocol,
        postgres_comparison_repository: CJComparisonRepositoryProtocol,
        postgres_essay_repository: CJEssayRepositoryProtocol,
    ) -> None:
        """Test that scores are correctly persisted to database."""
        # Create batch
        batch_id, essays = await self._create_test_batch(
            postgres_data_access,
            postgres_session,
            3,
        )

        # Initial check - essays should have no scores
        stmt = select(ProcessedEssay).where(ProcessedEssay.cj_batch_id == batch_id)
        result = await postgres_session.execute(stmt)
        initial_essays = result.scalars().all()

        for essay in initial_essays:
            assert essay.current_bt_score is None
            assert essay.current_bt_se is None
            assert essay.comparison_count == 0

        # Add comparisons and compute scores
        comparisons = [(0, 1, "a"), (1, 2, "a"), (0, 2, "a")]
        results = self._create_comparison_results(essays, comparisons)

        scores = await record_comparisons_and_update_scores(
            all_essays=essays,
            comparison_results=results,
            session_provider=postgres_session_provider,
            comparison_repository=postgres_comparison_repository,
            essay_repository=postgres_essay_repository,
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
        )

        # Use a fresh session to see the committed updates
        async with postgres_session_provider.session() as fresh_session:
            result = await fresh_session.execute(stmt)
            updated_essays = result.scalars().all()

            for essay in updated_essays:
                assert essay.current_bt_score is not None, "Score missing"
                assert essay.current_bt_se is not None, "SE missing"
                assert essay.comparison_count > 0, "Count not updated"

                # Verify score matches returned value
                assert abs(essay.current_bt_score - scores[essay.els_essay_id]) < 1e-10

    async def test_get_essay_rankings(
        self,
        postgres_data_access: PostgresDataAccess,
        postgres_session: AsyncSession,
        postgres_session_provider: SessionProviderProtocol,
        postgres_comparison_repository: CJComparisonRepositoryProtocol,
        postgres_essay_repository: CJEssayRepositoryProtocol,
    ) -> None:
        """Test ranking generation from scores."""
        # Create batch and compute scores
        batch_id, essays = await self._create_test_batch(
            postgres_data_access,
            postgres_session,
            4,
        )

        comparisons = [
            (0, 1, "a"),
            (0, 2, "a"),
            (0, 3, "a"),  # 0 wins all
            (1, 2, "a"),
            (1, 3, "a"),  # 1 beats 2,3
            (2, 3, "a"),  # 2 beats 3
        ]

        results = self._create_comparison_results(essays, comparisons)
        await record_comparisons_and_update_scores(
            all_essays=essays,
            comparison_results=results,
            session_provider=postgres_session_provider,
            comparison_repository=postgres_comparison_repository,
            essay_repository=postgres_essay_repository,
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
        )

        # Get rankings
        rankings = await get_essay_rankings(
            session_provider=postgres_session_provider,
            essay_repository=postgres_essay_repository,
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
        )

        # Validate rankings
        assert len(rankings) == 4

        # Check rank ordering
        for i, ranking in enumerate(rankings):
            assert ranking["rank"] == i + 1
            assert "els_essay_id" in ranking
            assert "bradley_terry_score" in ranking
            assert "bradley_terry_se" in ranking
            assert "comparison_count" in ranking
            assert "is_anchor" in ranking

            # Scores should decrease
            if i > 0:
                assert ranking["bradley_terry_score"] <= rankings[i - 1]["bradley_terry_score"]

        # Verify expected order
        assert rankings[0]["els_essay_id"] == "essay_0"
        assert rankings[1]["els_essay_id"] == "essay_1"
        assert rankings[2]["els_essay_id"] == "essay_2"
        assert rankings[3]["els_essay_id"] == "essay_3"

    async def test_estimate_required_comparisons(self) -> None:
        """Test heuristic for estimating comparison requirements."""
        # Test with various essay counts
        test_cases = [
            (10, 0.1, 2.0),  # 10 essays, target SE 0.1
            (50, 0.1, 2.0),  # 50 essays
            (100, 0.05, 3.0),  # 100 essays, tighter SE
        ]

        for n_items, target_se, connectivity in test_cases:
            estimated = estimate_required_comparisons(n_items, target_se, connectivity)

            # Basic sanity checks
            assert estimated > 0
            assert estimated >= n_items * connectivity  # Minimum connectivity

            # Should scale roughly with n*log(n)
            expected_order = n_items * np.log(n_items) * connectivity
            assert estimated < expected_order * 10  # Within order of magnitude
