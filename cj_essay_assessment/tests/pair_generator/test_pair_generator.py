# mypy: disable-error-code=call-arg
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.cj_essay_assessment.config import LLMProviderDetails, Settings
# Imports for type hinting and objects under test
from src.cj_essay_assessment.models_api import EssayForComparison
from src.cj_essay_assessment.pair_generator import (
    _fetch_existing_comparison_ids, generate_comparison_tasks)


# Helper to create a Settings object for tests
def create_test_settings(
    comparison_iteration: int = 5,
    prompt_template: str = "A:{essay_a_id}-{essay_a_text}\nB:{essay_b_id}-{essay_b_text}",
) -> Settings:
    # This is a simplified way to create Settings for tests.
    # Ensure all required fields for Settings are provided with valid defaults.
    return Settings(
        database_url="sqlite+aiosqlite:///./test_db.db",  # Dummy URL
        log_level="DEBUG",
        default_provider="openrouter",
        llm_providers={"openrouter": LLMProviderDetails(api_base="http://localhost")},
        comparison_model="test/model",
        system_prompt="Test system prompt",
        assessment_prompt_template=prompt_template,
        temperature=0.1,
        max_tokens_response=50,
        max_pairwise_comparisons=100,
        score_stability_threshold=0.01,
        min_comparisons_for_stability_check=10,
        comparisons_per_stability_check_iteration=comparison_iteration,
        essay_input_dir="./data/",
        cache_enabled=False,
        cache_type="memory",
        cache_directory="./cache_data/api_cache",
        cache_ttl_seconds=3600,
        nlp_features_to_compute=["word_count"],
    )


@pytest.fixture
def test_settings() -> Settings:
    return create_test_settings()


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)

    # Configure the result of session.execute() to be a MagicMock
    mock_execute_result = MagicMock()
    # Configure the fetchall method on this MagicMock
    mock_execute_result.fetchall = MagicMock(
        return_value=[],
    )  # Default empty result for fetchall

    session.execute.return_value = mock_execute_result
    return session


@pytest.fixture
def sample_essays() -> list[EssayForComparison]:
    return [
        EssayForComparison(id=1, original_filename="e1.txt", text_content="Essay 1"),
        EssayForComparison(id=2, original_filename="e2.txt", text_content="Essay 2"),
        EssayForComparison(id=3, original_filename="e3.txt", text_content="Essay 3"),
        EssayForComparison(id=4, original_filename="e4.txt", text_content="Essay 4"),
    ]


@pytest.mark.asyncio
async def test_fetch_existing_comparison_ids_empty(mock_db_session: AsyncMock) -> None:
    # fetchall on the result of execute should return []
    mock_db_session.execute.return_value.fetchall.return_value = []
    existing_ids = await _fetch_existing_comparison_ids(mock_db_session, batch_id=1)
    assert existing_ids == set()
    mock_db_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_existing_comparison_ids_with_data(
    mock_db_session: AsyncMock,
) -> None:
    db_return = [(1, 2), (3, 1)]
    # fetchall on the result of execute should return db_return
    mock_db_session.execute.return_value.fetchall.return_value = db_return

    expected_ids: set[tuple[int, int]] = {
        cast("tuple[int, int]", tuple(sorted((1, 2)))),
        cast("tuple[int, int]", tuple(sorted((1, 3)))),
    }

    existing_ids = await _fetch_existing_comparison_ids(mock_db_session, batch_id=1)
    assert existing_ids == expected_ids


@pytest.mark.asyncio
async def test_generate_comparison_tasks_no_essays(
    mock_db_session: AsyncMock,
    test_settings: Settings,
) -> None:
    tasks = await generate_comparison_tasks([], mock_db_session, 1, test_settings)
    assert tasks == []


@pytest.mark.asyncio
async def test_generate_comparison_tasks_one_essay(
    mock_db_session: AsyncMock,
    sample_essays: list[EssayForComparison],
    test_settings: Settings,
) -> None:
    tasks = await generate_comparison_tasks(
        sample_essays[:1],
        mock_db_session,
        1,
        test_settings,
    )
    assert tasks == []


@pytest.mark.asyncio
async def test_generate_comparison_tasks_all_new_pairs(
    mock_db_session: AsyncMock,
    sample_essays: list[EssayForComparison],
    test_settings: Settings,
) -> None:
    # fetchall on the result of execute should return []
    # for _fetch_existing_comparison_ids
    mock_db_session.execute.return_value.fetchall.return_value = []

    tasks = await generate_comparison_tasks(
        sample_essays,
        mock_db_session,
        1,
        test_settings,
    )

    assert len(tasks) == test_settings.comparisons_per_stability_check_iteration
    assert len(tasks) == 5

    task_pairs_ids = {tuple(sorted((task.essay_a.id, task.essay_b.id))) for task in tasks}
    assert len(task_pairs_ids) == 5

    if tasks:
        first_task = tasks[0]
        assert str(first_task.essay_a.id) in first_task.prompt
        assert first_task.essay_a.text_content in first_task.prompt
        assert str(first_task.essay_b.id) in first_task.prompt
        assert first_task.essay_b.text_content in first_task.prompt
        assert test_settings.assessment_prompt_template.split("{")[0] in first_task.prompt


@pytest.mark.asyncio
async def test_generate_comparison_tasks_some_existing_pairs(
    mock_db_session: AsyncMock,
    sample_essays: list[EssayForComparison],
    test_settings: Settings,
) -> None:
    existing_db_pairs = [(1, 2), (1, 3)]
    # fetchall on the result of execute should return existing_db_pairs
    mock_db_session.execute.return_value.fetchall.return_value = existing_db_pairs

    tasks = await generate_comparison_tasks(
        sample_essays,
        mock_db_session,
        1,
        test_settings,
    )
    assert len(tasks) == 4

    task_ids_set = {tuple(sorted((t.essay_a.id, t.essay_b.id))) for t in tasks}
    expected_new_ids = {
        tuple(sorted((1, 4))),
        tuple(sorted((2, 3))),
        tuple(sorted((2, 4))),
        tuple(sorted((3, 4))),
    }
    assert task_ids_set == expected_new_ids


@pytest.mark.asyncio
async def test_generate_comparison_tasks_all_pairs_exist(
    mock_db_session: AsyncMock,
    sample_essays: list[EssayForComparison],
    test_settings: Settings,
) -> None:
    three_essays = sample_essays[:3]
    existing_db_pairs = [(1, 2), (1, 3), (2, 3)]
    # fetchall on the result of execute should return existing_db_pairs
    mock_db_session.execute.return_value.fetchall.return_value = existing_db_pairs

    tasks = await generate_comparison_tasks(
        three_essays,
        mock_db_session,
        1,
        test_settings,
    )
    assert len(tasks) == 0


@pytest.mark.asyncio
async def test_generate_comparison_tasks_randomness_mocked_shuffle(
    mock_db_session: AsyncMock,
    sample_essays: list[EssayForComparison],
    test_settings: Settings,
) -> None:
    # fetchall on the result of execute should return []
    mock_db_session.execute.return_value.fetchall.return_value = []
    test_settings.comparisons_per_stability_check_iteration = 6

    def mock_shuffle(x: list) -> None:
        x.reverse()

    with patch("src.cj_essay_assessment.pair_generator.random.shuffle", mock_shuffle):
        tasks_custom_shuffle = await generate_comparison_tasks(
            sample_essays,
            mock_db_session,
            1,
            test_settings,
        )

    with patch(
        "src.cj_essay_assessment.pair_generator.random.shuffle",
    ) as mock_actual_shuffle_call:
        tasks_default_shuffle = await generate_comparison_tasks(
            sample_essays,
            mock_db_session,
            1,
            test_settings,
        )
        mock_actual_shuffle_call.assert_called_once()

    assert len(tasks_custom_shuffle) == 6
    assert len(tasks_default_shuffle) == 6

    task_custom_ids = [
        tuple(sorted((t.essay_a.id, t.essay_b.id))) for t in tasks_custom_shuffle
    ]
    task_default_ids = [
        tuple(sorted((t.essay_a.id, t.essay_b.id))) for t in tasks_default_shuffle
    ]

    assert set(task_custom_ids) == set(task_default_ids)

    if len(sample_essays) > 2:
        assert task_custom_ids != task_default_ids, (
            "Mocked shuffle (reverse) resulted in same order as default shuffle, "
            "or too few items to test order."
        )


@pytest.mark.asyncio
async def test_generate_comparison_tasks_iteration_limit(
    mock_db_session: AsyncMock,
    sample_essays: list[EssayForComparison],
    test_settings: Settings,
) -> None:
    # fetchall on the result of execute should return []
    mock_db_session.execute.return_value.fetchall.return_value = []
    test_settings.comparisons_per_stability_check_iteration = 2

    tasks = await generate_comparison_tasks(
        sample_essays,
        mock_db_session,
        1,
        test_settings,
    )
    assert len(tasks) == 2

    test_settings.comparisons_per_stability_check_iteration = 0
    tasks_zero_limit = await generate_comparison_tasks(
        sample_essays,
        mock_db_session,
        1,
        test_settings,
    )
    assert len(tasks_zero_limit) == 0
