"""Tests for the Ranking Handler module.

This test suite covers functionality of the ranking_handler.py module, including:
- Recording comparison results to the database.
- Computing Bradley-Terry scores using the choix library.
- Updating essay scores in the database.
- Checking score stability between iterations.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from src.cj_essay_assessment.models_api import (ComparisonResult,
                                                ComparisonTask,
                                                EssayForComparison,
                                                LLMAssessmentResponseSchema)
from src.cj_essay_assessment.models_db import ComparisonPair, ProcessedEssay
from src.cj_essay_assessment.ranking_handler import (
    check_score_stability, get_essay_rankings,
    record_comparisons_and_update_scores)


@pytest.fixture
def sample_essays() -> list[EssayForComparison]:
    """Sample list of essays for testing."""
    return [
        EssayForComparison(
            id=1,
            original_filename="essay1.txt",
            text_content="Essay 1",
            current_bt_score=None,
        ),
        EssayForComparison(
            id=2,
            original_filename="essay2.txt",
            text_content="Essay 2",
            current_bt_score=None,
        ),
        EssayForComparison(
            id=3,
            original_filename="essay3.txt",
            text_content="Essay 3",
            current_bt_score=None,
        ),
    ]


@pytest.fixture
def sample_comparison_results(
    sample_essays: list[EssayForComparison],
) -> list[ComparisonResult]:
    """Sample list of comparison results for testing."""
    essay_a = sample_essays[0]
    essay_b = sample_essays[1]

    task = ComparisonTask(essay_a=essay_a, essay_b=essay_b, prompt="Compare these essays")

    assessment = LLMAssessmentResponseSchema(
        winner="Essay A",
        justification="Essay A is better structured",
        confidence=4.2,
    )

    return [
        ComparisonResult(
            task=task,
            llm_assessment=assessment,
            raw_llm_response_content=(
                '{"winner": "Essay A", "justification": "Essay A is better structured", '
                '"confidence": 4.2}'
            ),
            error_message=None,
            from_cache=False,
            prompt_hash="abc123",
        ),
    ]


@pytest.fixture
def mock_db_handler() -> tuple[MagicMock, AsyncMock]:
    """Mock DatabaseHandler for testing."""
    mock_handler = MagicMock()

    # Mock session as async context manager
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    session_context = AsyncMock()
    session_context.__aenter__.return_value = mock_session
    session_context.__aexit__.return_value = None
    mock_handler.session.return_value = session_context

    return mock_handler, mock_session


# --- Tests for record_comparisons_and_update_scores ---


@pytest.mark.asyncio
@patch("src.cj_essay_assessment.ranking_handler.choix.ilsr_pairwise")
async def test_record_comparisons_creates_db_entries(
    mock_ilsr_pairwise: MagicMock,
    mock_db_handler: tuple[MagicMock, AsyncMock],
    sample_essays: list[EssayForComparison],
    sample_comparison_results: list[ComparisonResult],
) -> None:
    """Test that comparison results are correctly recorded in the database."""
    mock_handler, mock_session = mock_db_handler

    # Mock session.execute and its result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    # Call the function under test
    await record_comparisons_and_update_scores(
        mock_handler,
        batch_id=1,
        iteration=1,
        results=sample_comparison_results,
        all_essays=sample_essays,
    )

    # Check that comparison was added to the session
    assert mock_session.add.called
    comparison_pair = mock_session.add.call_args[0][0]
    assert isinstance(comparison_pair, ComparisonPair)
    assert comparison_pair.batch_id == 1
    assert comparison_pair.essay_a_id == 1
    assert comparison_pair.essay_b_id == 2
    # Access instance attributes correctly based on the model definition
    assert comparison_pair.winner == "essay_a"  # Essay A won
    assert comparison_pair.processing_metadata == {"comparison_batch_iteration": 1}


@pytest.mark.asyncio
@patch("src.cj_essay_assessment.ranking_handler.choix.ilsr_pairwise")
async def test_update_scores_calls_choix_correctly(
    mock_ilsr_pairwise: MagicMock,
    mock_db_handler: tuple[MagicMock, AsyncMock],
    sample_essays: list[EssayForComparison],
) -> None:
    """Test that choix library is called with the correct parameters."""
    mock_handler, mock_session = mock_db_handler

    # Create some existing comparison pairs in the DB
    existing_comparisons = [
        MagicMock(
            spec=ComparisonPair,
            batch_id=1,
            essay_a_id=1,
            essay_b_id=2,
            winner="essay_a",
        ),
        MagicMock(
            spec=ComparisonPair,
            batch_id=1,
            essay_a_id=2,
            essay_b_id=3,
            winner="essay_a",
        ),
        MagicMock(
            spec=ComparisonPair,
            batch_id=1,
            essay_a_id=1,
            essay_b_id=3,
            winner="essay_a",
        ),
    ]

    # Mock session.execute and its result to return existing comparisons
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = existing_comparisons
    mock_session.execute.return_value = mock_result

    # Mock the choix.ilsr_pairwise result
    mock_ilsr_pairwise.return_value = np.array([0.5, 0.0, -0.5])

    # Call the function under test with an empty results list
    # (we're testing the scoring part)
    await record_comparisons_and_update_scores(
        mock_handler,
        batch_id=1,
        iteration=2,  # Next iteration
        results=[],  # No new comparisons
        all_essays=sample_essays,
    )

    # Check that choix.ilsr_pairwise was called correctly
    mock_ilsr_pairwise.assert_called_once()
    args, kwargs = mock_ilsr_pairwise.call_args

    # First arg should be the number of items (essays)
    assert args[0] == 3

    # Second arg should be a list of (winner_idx, loser_idx) tuples
    comparisons = args[1]
    assert len(comparisons) == 3
    # Note: With the updated logic, expectations change
    # because we're using winner="essay_a"
    # which means essay A wins in all cases
    assert (
        0,
        1,
    ) in comparisons  # essay 1 beat essay 2 (essay_a = essay1, essay_b = essay2)
    assert (
        0,
        2,
    ) in comparisons  # essay 1 beat essay 3 (essay_a = essay1, essay_b = essay3)
    # The second comparison has essay_a=essay2 and essay_b=essay3, with essay_a winning
    assert (1, 2) in comparisons  # essay 2 beat essay 3

    # Check alpha was passed for regularization
    assert kwargs.get("alpha") == 0.01


@pytest.mark.asyncio
@patch("src.cj_essay_assessment.ranking_handler.choix.ilsr_pairwise")
async def test_update_scores_updates_essay_bt_scores_in_db(
    mock_ilsr_pairwise: MagicMock,
    mock_db_handler: tuple[MagicMock, AsyncMock],
    sample_essays: list[EssayForComparison],
) -> None:
    """Test that essay BT scores are updated in the database."""
    mock_handler, mock_session = mock_db_handler

    # Create some existing comparison pairs in the DB
    existing_comparisons = [
        MagicMock(
            spec=ComparisonPair,
            batch_id=1,
            essay_a_id=1,
            essay_b_id=2,
            winner="essay_a",
        ),
        MagicMock(
            spec=ComparisonPair,
            batch_id=1,
            essay_a_id=2,
            essay_b_id=3,
            winner="essay_a",
        ),
        MagicMock(
            spec=ComparisonPair,
            batch_id=1,
            essay_a_id=1,
            essay_b_id=3,
            winner="essay_a",
        ),
    ]

    # Mock session.execute for fetching comparisons
    comparisons_result = MagicMock()
    comparisons_result.scalars.return_value.all.return_value = existing_comparisons

    # Mock results for fetching essays
    essay_results = []
    for essay_id in range(1, 4):  # Essays 1-3
        essay_result = MagicMock()
        essay = MagicMock(spec=ProcessedEssay, id=essay_id)
        essay_result.scalar_one_or_none.return_value = essay
        essay_results.append(essay_result)

    # Set up the session.execute to return different results based on the query
    mock_session.execute.side_effect = [comparisons_result] + essay_results

    # Mock the choix.ilsr_pairwise result - mean will be 0.0
    mock_ilsr_pairwise.return_value = np.array([0.5, 0.0, -0.5])

    # Call the function under test
    result = await record_comparisons_and_update_scores(
        mock_handler,
        batch_id=1,
        iteration=2,
        results=[],  # No new comparisons
        all_essays=sample_essays,
    )

    # Check that the scores were updated in the DB
    # We expect 3 essays with scores: 0.5, 0.0, -0.5
    assert len(result) == 3
    assert result[1] == 0.5
    assert result[2] == 0.0
    assert result[3] == -0.5


# --- Tests for check_score_stability ---


def test_check_stability_below_threshold() -> None:
    """Test that stability calculation works for small changes."""
    current_scores = {1: 0.5, 2: 0.1, 3: -0.6}
    previous_scores = {1: 0.51, 2: 0.09, 3: -0.6}

    # Max difference should be 0.01 (for essay 1: 0.51 - 0.5)
    max_change = check_score_stability(current_scores, previous_scores)
    assert abs(max_change - 0.01) < 1e-10  # Allow for floating point imprecision


def test_check_stability_above_threshold() -> None:
    """Test that stability calculation works for large changes."""
    current_scores = {1: 0.5, 2: 0.1, 3: -0.6}
    previous_scores = {1: 0.4, 2: 0.3, 3: -0.7}

    # Max difference should be 0.2 (for essay 2: 0.3 - 0.1)
    max_change = check_score_stability(current_scores, previous_scores)
    assert abs(max_change - 0.2) < 1e-10  # Allow for floating point imprecision


def test_check_stability_with_missing_essays() -> None:
    """Test that stability calculation handles missing essays."""
    current_scores = {1: 0.5, 2: 0.1, 3: -0.6}
    previous_scores = {1: 0.4, 3: -0.7}  # Essay 2 missing

    # Max difference should be 0.1 (for essay 3: -0.6 - -0.7)
    # For essay 2, it would be 0.1 - 0.0 = 0.1, which is not max
    max_change = check_score_stability(current_scores, previous_scores)
    assert abs(max_change - 0.1) < 1e-10  # Allow for floating point imprecision


def test_check_stability_with_empty_scores() -> None:
    """Test that stability calculation handles empty score sets."""
    # No stability if one set is empty - return infinity
    assert check_score_stability({1: 0.5}, {}) == float("inf")
    assert check_score_stability({}, {1: 0.5}) == float("inf")
    assert check_score_stability({}, {}) == float("inf")


# --- Tests for get_essay_rankings ---


@pytest.mark.asyncio
async def test_get_essay_rankings(mock_db_handler: tuple[MagicMock, AsyncMock]) -> None:
    """Test fetching and ranking essays by BT score."""
    mock_handler, mock_session = mock_db_handler

    # Create mock essays with BT scores, already in descending order by BT score
    # as they would come back from a SQL query with ORDER BY
    mock_essays = [
        MagicMock(
            spec=ProcessedEssay,
            id=1,
            original_filename="essay1.txt",
            current_bt_score=0.8,
        ),
        MagicMock(
            spec=ProcessedEssay,
            id=3,
            original_filename="essay3.txt",
            current_bt_score=0.5,
        ),
        MagicMock(
            spec=ProcessedEssay,
            id=2,
            original_filename="essay2.txt",
            current_bt_score=0.3,
        ),
    ]

    # Mock session.execute for fetching essays
    essays_result = MagicMock()
    essays_result.scalars.return_value.all.return_value = mock_essays
    mock_session.execute.return_value = essays_result

    # Call the function under test
    rankings = await get_essay_rankings(mock_handler, batch_id=1)

    # Check the rankings
    assert len(rankings) == 3

    # Essays should be ranked in descending order of BT score
    assert rankings[0]["id"] == 1
    assert rankings[0]["rank"] == 1
    assert rankings[0]["bt_score"] == 0.8

    assert rankings[1]["id"] == 3
    assert rankings[1]["rank"] == 2
    assert rankings[1]["bt_score"] == 0.5

    assert rankings[2]["id"] == 2
    assert rankings[2]["rank"] == 3
    assert rankings[2]["bt_score"] == 0.3
