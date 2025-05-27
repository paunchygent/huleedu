from collections.abc import Awaitable  # Added Awaitable
from collections.abc import Callable  # Added Callable
from typing import Any
from unittest.mock import AsyncMock  # For type hinting

import pytest
from pytest_mock import MockerFixture
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession  # For type hinting

# Assuming these are your actual paths and models
from src.cj_essay_assessment.db.models_db import User
from src.cj_essay_assessment.llm_caller import (ComparisonResult,
                                                ComparisonTask,
                                                process_comparison_tasks_async)
from src.cj_essay_assessment.models_api import (  # Added LLMAssessmentResponseSchema
    EssayForComparison, LLMAssessmentResponseSchema)


@pytest.mark.asyncio
async def test_db_session_fixture(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:  # Corrected type hint
    """Tests that the db_session fixture works and we can interact with the database.
    It uses the user_factory to create a user.
    """
    # Arrange: Use the factory to create a user
    test_username = "fixture_test_user"
    created_user: User = await user_factory(
        username=test_username,
        email=f"{test_username}@example.com",
    )

    assert created_user is not None
    assert created_user.id is not None
    assert created_user.username == test_username

    # Act: Try to fetch the user from the database within the same session
    stmt = select(User).where(User.id == created_user.id)
    result = await db_session.execute(stmt)
    retrieved_user = result.scalar_one_or_none()

    # Assert: Check if the fetched user is the same as the created one
    assert retrieved_user is not None
    assert retrieved_user.id == created_user.id
    assert retrieved_user.username == test_username
    print(f"\nSuccessfully created and retrieved user: {retrieved_user.username}")


@pytest.mark.asyncio
async def test_mock_llm_caller_interaction(
    mocker: MockerFixture,
) -> None:  # Added return type hint
    """Tests that mocking process_comparison_tasks_async in llm_caller works.
    Uses mocker directly within the test.
    """
    # Arrange: Create a mock for process_comparison_tasks_async
    # Patch the function *where it is used* in this module's scope.
    mock_process_tasks = mocker.patch(
        "tests.integration.test_core_fixtures.process_comparison_tasks_async",
        new_callable=AsyncMock,
    )

    # Define the mock's side effect (what it should return)
    async def mock_side_effect(
        tasks: list[ComparisonTask],
        *args: Any,
        **kwargs: Any,
    ) -> list[ComparisonResult]:
        results = []
        for task_item in tasks:
            mock_assessment = LLMAssessmentResponseSchema(
                winner="Essay A",
                justification="Mocked: Essay A was preferred.",
                confidence=4.5,
            )
            results.append(
                ComparisonResult(
                    task=task_item,
                    llm_assessment=mock_assessment,
                    raw_llm_response_content="{}",
                    from_cache=False,
                    prompt_hash="mock_hash",
                ),
            )
        return results

    mock_process_tasks.side_effect = mock_side_effect

    # Create sample ComparisonTask(s)
    essay_a_comp = EssayForComparison(
        id=1,
        original_filename="a.txt",
        text_content="Essay A content",
    )
    essay_b_comp = EssayForComparison(
        id=2,
        original_filename="b.txt",
        text_content="Essay B content",
    )
    sample_task = ComparisonTask(
        essay_a=essay_a_comp,
        essay_b=essay_b_comp,
        prompt="Test prompt for LLM fixture",
    )
    tasks_to_process = [sample_task]

    # Act: Call the (now patched) function
    results = await process_comparison_tasks_async(tasks_to_process)

    # Assert
    mock_process_tasks.assert_awaited_once_with(tasks_to_process)
    assert results is not None
    assert len(results) == 1
    single_result = results[0]
    assert isinstance(single_result, ComparisonResult)
    assert single_result.task == sample_task
    assert single_result.llm_assessment is not None  # Added check for None
    assert single_result.llm_assessment.winner == "Essay A"

    print(
        f"\nSuccessfully called mocked LLM (patched in test) and got {len(results)} result(s).",
    )
    print(f"Mock call count: {mock_process_tasks.await_count}")
