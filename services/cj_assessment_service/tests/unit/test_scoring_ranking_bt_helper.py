from __future__ import annotations

from statistics import fmean
from uuid import uuid4

import pytest
from huleedu_service_libs.error_handling import HuleEduError

from services.cj_assessment_service.cj_core_logic.scoring_ranking import (
    BTScoringResult,
    compute_bt_scores_and_se,
)
from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.models_db import ComparisonPair as CJ_ComparisonPair


class TestBTScoringHelper:
    """Unit tests for compute_bt_scores_and_se BT helper."""

    def _make_essays(self) -> list[EssayForComparison]:
        return [
            EssayForComparison(id="essay_1", text_content="First essay"),
            EssayForComparison(id="essay_2", text_content="Second essay"),
        ]

    def _make_comparisons(self, cj_batch_id: int) -> list[CJ_ComparisonPair]:
        # Single deterministic comparison: essay_1 beats essay_2
        return [
            CJ_ComparisonPair(
                cj_batch_id=cj_batch_id,
                essay_a_els_id="essay_1",
                essay_b_els_id="essay_2",
                winner="essay_a",
                prompt_text="Compare the essays",
            ),
        ]

    def test_compute_bt_scores_and_se_basic_properties(self) -> None:
        """Helper returns mean-centred scores, SEs, counts and diagnostics."""
        cj_batch_id = 123
        correlation_id = uuid4()

        essays = self._make_essays()
        comparisons = self._make_comparisons(cj_batch_id)

        result = compute_bt_scores_and_se(
            all_essays=essays,
            comparisons=comparisons,
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        assert isinstance(result, BTScoringResult)

        # Scores exist for each essay and are mean-centred
        assert set(result.scores.keys()) == {"essay_1", "essay_2"}
        assert len(result.scores) == len(essays)
        mean_score = fmean(result.scores.values())
        assert abs(mean_score) < 1e-10

        # SEs exist for each essay and are finite
        assert set(result.ses.keys()) == {"essay_1", "essay_2"}
        for se_val in result.ses.values():
            assert se_val >= 0.0

        # Comparison counts reflect the single pair
        assert result.per_essay_counts["essay_1"] == 1
        assert result.per_essay_counts["essay_2"] == 1

        # SE summary exposes the expected diagnostics shape
        se_summary = result.se_summary
        expected_keys = {
            "mean_se",
            "max_se",
            "min_se",
            "item_count",
            "comparison_count",
            "items_at_cap",
            "isolated_items",
            "mean_comparisons_per_item",
            "min_comparisons_per_item",
            "max_comparisons_per_item",
        }
        assert expected_keys.issubset(se_summary.keys())
        assert se_summary["item_count"] == len(essays)
        assert se_summary["comparison_count"] == len(comparisons)
        assert se_summary["isolated_items"] == 0

    def test_compute_bt_scores_and_se_raises_for_no_comparisons(self) -> None:
        """Helper raises CJ domain error when no usable comparisons exist."""
        cj_batch_id = 456
        correlation_id = uuid4()

        essays = self._make_essays()

        with pytest.raises(HuleEduError):
            compute_bt_scores_and_se(
                all_essays=essays,
                comparisons=[],
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )
