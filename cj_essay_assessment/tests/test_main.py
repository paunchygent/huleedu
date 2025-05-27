"""Tests for the main script."""

import asyncio
import tempfile
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, PropertyMock, patch

import pytest

from src.cj_essay_assessment.main import (configure_logging, main_entry_point,
                                          parse_arguments,
                                          run_comparative_judgment_for_batch)
from src.cj_essay_assessment.models_db import BatchStatusEnum


def create_mock_settings():
    """Create a properly configured mock settings object for tests.

    This prevents the creation of MagicMock-named directories when
    cache_directory_path is accessed.
    """
    mock_settings = MagicMock()

    # Create a temporary directory for testing that will be automatically cleaned up
    temp_cache_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_cache_dir.name)

    # Configure the cache_directory_path property to return our temp path
    type(mock_settings).cache_directory_path = PropertyMock(return_value=temp_path)

    # Store the temp_dir reference so it doesn't get garbage collected
    mock_settings._temp_cache_dir = temp_cache_dir

    return mock_settings


@pytest.mark.asyncio
async def test_run_comparative_judgment_no_essays() -> None:
    """Test the main function with no essays."""
    # Mock all dependencies
    with (
        patch("src.cj_essay_assessment.main.DatabaseHandler") as mock_db_handler_class,
        patch("src.cj_essay_assessment.main.get_settings") as mock_get_settings,
        patch(
            "src.cj_essay_assessment.main.process_essays_for_batch",
            return_value=[],
        ) as mock_process_essays,
        patch(
            "src.cj_essay_assessment.main.compute_and_store_nlp_stats",
        ) as mock_compute_nlp,
    ):
        # Setup mocks
        mock_db_handler_instance = AsyncMock()
        mock_db_handler_instance.create_tables = AsyncMock()
        mock_db_handler_instance.update_batch_status = AsyncMock()
        # Proper async context manager for session
        mock_session_cm = AsyncMock()
        mock_session = AsyncMock()
        mock_session_cm.__aenter__.return_value = mock_session
        mock_session_cm.__aexit__.return_value = None
        mock_db_handler_instance.session = MagicMock(return_value=mock_session_cm)
        mock_db_handler_class.return_value = mock_db_handler_instance

        mock_settings = create_mock_settings()
        mock_get_settings.return_value = mock_settings

        # Run the function
        success = await run_comparative_judgment_for_batch(1)

        # Assert
        assert success is False
        mock_db_handler_instance.create_tables.assert_awaited_once()
        mock_process_essays.assert_awaited_once_with(
            mock_db_handler_instance,
            mock_settings,
            1,
        )
        mock_compute_nlp.assert_not_awaited()
        # Check that update_batch_status was NOT called by main.py for
        # NLP/Comparison stages. This test ensures main.py exits early.
        main_py_status_update_calls = [
            c
            for c in mock_db_handler_instance.update_batch_status.await_args_list
            if c[0][1] == 1  # Check args passed to await (batch_id)
        ]
        # Assert main.py didn't set its specific statuses
        assert not any(
            call_args[0][2]
            in [
                BatchStatusEnum.PROCESSING_NLP,
                BatchStatusEnum.READY_FOR_COMPARISON,
                BatchStatusEnum.PERFORMING_COMPARISONS,
                BatchStatusEnum.ERROR_NLP,
                BatchStatusEnum.ERROR_COMPARISON,
                BatchStatusEnum.COMPLETE_STABLE,
                BatchStatusEnum.COMPLETE_MAX_COMPARISONS,
            ]
            for call_args in main_py_status_update_calls
        )


@pytest.mark.asyncio
async def test_run_comparative_judgment_unexpected_early_error(
    capsys,
):
    """Test that an unexpected error early in the CJ process sets ERROR_COMPARISON and logs."""
    batch_id_to_test = 42

    import sys

    from loguru import logger

    handler_id = logger.add(sys.stderr, level="ERROR")
    try:
        with (
            patch(
                "src.cj_essay_assessment.main.DatabaseHandler"
            ) as mock_db_handler_class,
            patch("src.cj_essay_assessment.main.get_settings") as mock_get_settings,
        ):
            mock_db_handler_instance = AsyncMock()
            # Simulate create_tables raising an unexpected error
            mock_db_handler_instance.create_tables = AsyncMock(
                side_effect=Exception("Early Boom!")
            )
            mock_db_handler_instance.update_batch_status = AsyncMock()
            # Proper async context manager for session
            mock_session_cm = AsyncMock()
            mock_session = AsyncMock()
            mock_session_cm.__aenter__.return_value = mock_session
            mock_session_cm.__aexit__.return_value = None
            mock_db_handler_instance.session = MagicMock(return_value=mock_session_cm)
            mock_db_handler_class.return_value = mock_db_handler_instance

            mock_settings = create_mock_settings()
            mock_get_settings.return_value = mock_settings

            # Run the function (should hit the fallback error handler)
            result = await run_comparative_judgment_for_batch(batch_id_to_test)

            assert result is False
            # Should have attempted to set ERROR_COMPARISON
            update_calls = mock_db_handler_instance.update_batch_status.await_args_list
            assert any(
                c.args[1] == batch_id_to_test
                and c.args[2] == BatchStatusEnum.ERROR_COMPARISON
                for c in update_calls
            ), f"Did not set ERROR_COMPARISON, calls: {update_calls}"
            # Should log the exception
            stderr = capsys.readouterr().err
            assert "Early Boom!" in stderr
    finally:
        logger.remove(handler_id)


@pytest.mark.asyncio
async def test_run_comparative_judgment_with_essays_stable() -> None:
    """Test the main function with essays that reach stability."""
    # Mock all dependencies
    with (
        patch("src.cj_essay_assessment.main.DatabaseHandler") as mock_db_handler_class,
        patch("src.cj_essay_assessment.main.get_settings") as mock_get_settings,
        patch(
            "src.cj_essay_assessment.main.process_essays_for_batch",
        ) as mock_process_essays,
        patch(
            "src.cj_essay_assessment.main.compute_and_store_nlp_stats",
        ) as mock_compute_nlp,
        patch(
            "src.cj_essay_assessment.main.generate_comparison_tasks",
        ) as mock_generate_tasks,
        patch(
            "src.cj_essay_assessment.main.process_comparison_tasks_async",
        ) as mock_process_tasks,
        patch(
            "src.cj_essay_assessment.main.record_comparisons_and_update_scores",
        ) as mock_record_update,
        patch(
            "src.cj_essay_assessment.main.check_score_stability",
            return_value=0.001,
        ) as mock_check_stability,
        patch(
            "src.cj_essay_assessment.ranking_handler.get_essay_rankings",
            new_callable=AsyncMock,
        ) as mock_get_rankings,
    ):
        # Setup mocks
        mock_db_handler_instance = AsyncMock()
        mock_db_handler_instance.create_tables = AsyncMock()
        mock_db_handler_instance.update_batch_status = AsyncMock()
        # Proper async context manager for session
        mock_session_cm = AsyncMock()
        mock_session = AsyncMock()
        mock_session_cm.__aenter__.return_value = mock_session
        mock_session_cm.__aexit__.return_value = None
        mock_db_handler_instance.session = MagicMock(return_value=mock_session_cm)
        mock_db_handler_class.return_value = mock_db_handler_instance

        # Configure settings
        mock_settings = create_mock_settings()
        mock_settings.max_pairwise_comparisons = 100
        mock_settings.min_comparisons_for_stability_check = 5
        mock_settings.score_stability_threshold = 0.01
        mock_get_settings.return_value = mock_settings

        # Setup essay mocks
        mock_essays = [MagicMock(id=i + 1) for i in range(3)]
        mock_process_essays.return_value = mock_essays

        # Setup comparison task mocks
        mock_tasks = [MagicMock() for _ in range(2)]
        mock_generate_tasks.return_value = mock_tasks

        # Setup result mocks
        mock_results = [MagicMock() for _ in range(2)]
        for i, result in enumerate(mock_results):
            result.llm_assessment = MagicMock()
            result.llm_assessment.winner = "Essay A" if i % 2 == 0 else "Essay B"
        mock_process_tasks.return_value = mock_results

        # Setup scores mock - this should trigger stability check
        mock_scores = {1: 1.0, 2: 0.5, 3: -1.5}
        mock_record_update.return_value = mock_scores

        # Run the function
        batch_id_to_test = 1
        success = await run_comparative_judgment_for_batch(batch_id_to_test)

        # Assert
        assert success is True
        mock_db_handler_instance.create_tables.assert_awaited_once()
        mock_process_essays.assert_awaited_once_with(
            mock_db_handler_instance,
            mock_settings,
            batch_id_to_test,
        )
        mock_compute_nlp.assert_awaited_once_with(
            mock_db_handler_instance,
            mock_settings,
            mock_essays,
        )
        assert mock_generate_tasks.await_count > 0
        assert mock_process_tasks.await_count > 0
        assert mock_record_update.await_count > 0
        assert mock_check_stability.call_count > 0
        mock_get_rankings.assert_called_once()

        # Assert status updates
        # Check specific calls related to main.py logic are made.
        actual_calls = mock_db_handler_instance.update_batch_status.await_args_list

        # Check PROCESSING_NLP
        assert any(
            c.args[1] == batch_id_to_test and c.args[2] == BatchStatusEnum.PROCESSING_NLP
            for c in actual_calls
        ), "PROCESSING_NLP status not set"

        # Check READY_FOR_COMPARISON
        assert any(
            c.args[1] == batch_id_to_test
            and c.args[2] == BatchStatusEnum.READY_FOR_COMPARISON
            for c in actual_calls
        ), "READY_FOR_COMPARISON status not set"

        # Check PERFORMING_COMPARISONS
        assert any(
            c.args[1] == batch_id_to_test
            and c.args[2] == BatchStatusEnum.PERFORMING_COMPARISONS
            for c in actual_calls
        ), "PERFORMING_COMPARISONS status not set"

        # Check COMPLETE_STABLE
        assert any(
            c.args[1] == batch_id_to_test and c.args[2] == BatchStatusEnum.COMPLETE_STABLE
            for c in actual_calls
        ), "COMPLETE_STABLE status not set"


@pytest.mark.asyncio
async def test_run_comparative_judgment_max_comparisons() -> None:
    """Test the main function reaching max comparisons without stability."""
    # Mock all dependencies
    with (
        patch("src.cj_essay_assessment.main.DatabaseHandler") as mock_db_handler_class,
        patch("src.cj_essay_assessment.main.get_settings") as mock_get_settings,
        patch(
            "src.cj_essay_assessment.main.process_essays_for_batch",
        ) as mock_process_essays,
        patch(
            "src.cj_essay_assessment.main.compute_and_store_nlp_stats",
        ) as mock_compute_nlp,
        patch(
            "src.cj_essay_assessment.main.generate_comparison_tasks",
        ) as mock_generate_tasks,
        patch(
            "src.cj_essay_assessment.main.process_comparison_tasks_async",
        ) as mock_process_tasks,
        patch(
            "src.cj_essay_assessment.main.record_comparisons_and_update_scores",
        ) as mock_record_update,
        patch(
            "src.cj_essay_assessment.main.check_score_stability",
            return_value=0.1,
        ) as mock_check_stability,
    ):
        # Setup mocks
        mock_db_handler_instance = AsyncMock()
        mock_db_handler_instance.create_tables = AsyncMock()
        mock_db_handler_instance.update_batch_status = AsyncMock()
        # Proper async context manager for session
        mock_session_cm = AsyncMock()
        mock_session = AsyncMock()
        mock_session_cm.__aenter__.return_value = mock_session
        mock_session_cm.__aexit__.return_value = None
        mock_db_handler_instance.session = MagicMock(return_value=mock_session_cm)
        mock_db_handler_class.return_value = mock_db_handler_instance

        # Configure settings - set max comparisons low
        mock_settings = create_mock_settings()
        mock_settings.max_pairwise_comparisons = 10
        mock_settings.min_comparisons_for_stability_check = 5
        mock_settings.score_stability_threshold = 0.01
        mock_get_settings.return_value = mock_settings

        # Setup essay mocks
        mock_essays = [MagicMock(id=i + 1) for i in range(3)]
        mock_process_essays.return_value = mock_essays

        # Setup comparison task mocks - each iteration will do 5 tasks
        mock_tasks = [MagicMock() for _ in range(5)]
        mock_generate_tasks.return_value = mock_tasks

        # Setup result mocks
        mock_results = [MagicMock() for _ in range(5)]
        for i, result in enumerate(mock_results):
            result.llm_assessment = MagicMock()
            result.llm_assessment.winner = "Essay A" if i % 2 == 0 else "Essay B"
        mock_process_tasks.return_value = mock_results

        # Setup scores mock
        mock_scores = {1: 1.0, 2: 0.5, 3: -1.5}
        mock_record_update.return_value = mock_scores

        # Run the function
        batch_id_to_test = 2
        success = await run_comparative_judgment_for_batch(batch_id_to_test)

        # Assert
        assert success is True
        mock_db_handler_instance.create_tables.assert_awaited_once()
        mock_process_essays.assert_awaited_once_with(
            mock_db_handler_instance,
            mock_settings,
            batch_id_to_test,
        )
        mock_compute_nlp.assert_awaited_once_with(
            mock_db_handler_instance,
            mock_settings,
            mock_essays,
        )
        assert mock_generate_tasks.await_count > 1
        assert mock_process_tasks.await_count > 1
        assert mock_record_update.await_count > 1
        assert mock_check_stability.call_count > 0

        # Assert status updates - should end with COMPLETE_MAX_COMPARISONS
        actual_calls = mock_db_handler_instance.update_batch_status.await_args_list
        assert any(
            c.args[1] == batch_id_to_test and c.args[2] == BatchStatusEnum.PROCESSING_NLP
            for c in actual_calls
        ), "PROCESSING_NLP status not set"
        assert any(
            c.args[1] == batch_id_to_test
            and c.args[2] == BatchStatusEnum.READY_FOR_COMPARISON
            for c in actual_calls
        ), "READY_FOR_COMPARISON status not set"
        assert any(
            c.args[1] == batch_id_to_test
            and c.args[2] == BatchStatusEnum.PERFORMING_COMPARISONS
            for c in actual_calls
        ), "PERFORMING_COMPARISONS status not set"
        assert any(
            c.args[1] == batch_id_to_test
            and c.args[2] == BatchStatusEnum.COMPLETE_MAX_COMPARISONS
            for c in actual_calls
        ), "COMPLETE_MAX_COMPARISONS status not set"


@pytest.mark.asyncio
async def test_run_comparative_judgment_nlp_failure() -> None:
    """Test the main function when NLP analysis fails."""
    batch_id_to_test = 3
    with (
        patch("src.cj_essay_assessment.main.DatabaseHandler") as mock_db_handler_class,
        patch("src.cj_essay_assessment.main.get_settings") as mock_get_settings,
        patch(
            "src.cj_essay_assessment.main.process_essays_for_batch",
        ) as mock_process_essays,
        patch(
            "src.cj_essay_assessment.main.compute_and_store_nlp_stats",
            side_effect=ValueError("NLP Boom!"),
        ) as mock_compute_nlp,
        patch(
            "src.cj_essay_assessment.main.generate_comparison_tasks",
        ) as mock_generate_tasks,
        patch(
            "src.cj_essay_assessment.main.process_comparison_tasks_async",
        ) as mock_process_tasks,
    ):
        mock_db_handler_instance = AsyncMock()
        mock_db_handler_instance.create_tables = AsyncMock()
        mock_db_handler_instance.update_batch_status = AsyncMock()
        # Proper async context manager for session
        mock_session_cm = AsyncMock()
        mock_session = AsyncMock()
        mock_session_cm.__aenter__.return_value = mock_session
        mock_session_cm.__aexit__.return_value = None
        mock_db_handler_instance.session = MagicMock(return_value=mock_session_cm)
        mock_db_handler_class.return_value = mock_db_handler_instance

        mock_settings = create_mock_settings()
        mock_get_settings.return_value = mock_settings

        mock_essays = [MagicMock(id=i + 1) for i in range(3)]
        mock_process_essays.return_value = mock_essays

        success = await run_comparative_judgment_for_batch(batch_id_to_test)

        assert success is False
        mock_db_handler_instance.create_tables.assert_awaited_once()
        mock_process_essays.assert_awaited_once()
        mock_compute_nlp.assert_awaited_once()
        mock_generate_tasks.assert_not_awaited()
        mock_process_tasks.assert_not_awaited()

        # Assert status updates: PROCESSING_NLP attempted, then ERROR_NLP set
        actual_calls = mock_db_handler_instance.update_batch_status.await_args_list
        call_args = [(c.args[1], c.args[2]) for c in actual_calls]

        expected_sequence = [
            (batch_id_to_test, BatchStatusEnum.PROCESSING_NLP),
            (batch_id_to_test, BatchStatusEnum.ERROR_NLP),
        ]

        # Check if the expected sequence appears in the actual calls
        # Find the index of the first expected call
        try:
            start_index = call_args.index(expected_sequence[0])
            # Check if the subsequent calls match the rest of the sequence
            assert (
                call_args[start_index : start_index + len(expected_sequence)]
                == expected_sequence
            )
        except ValueError:
            pytest.fail(
                f"Did not find expected status update sequence {expected_sequence} "
                f"in {call_args}",
            )


@pytest.mark.asyncio
async def test_run_comparative_judgment_comparison_loop_failure() -> None:
    """Test the main function when an error occurs within the comparison loop."""
    batch_id_to_test = 4
    with (
        patch("src.cj_essay_assessment.main.DatabaseHandler") as mock_db_handler_class,
        patch("src.cj_essay_assessment.main.get_settings") as mock_get_settings,
        patch(
            "src.cj_essay_assessment.main.process_essays_for_batch",
        ) as mock_process_essays,
        patch(
            "src.cj_essay_assessment.main.compute_and_store_nlp_stats",
        ) as mock_compute_nlp,
        patch(
            "src.cj_essay_assessment.main.generate_comparison_tasks",
        ) as mock_generate_tasks,
        patch(
            "src.cj_essay_assessment.main.process_comparison_tasks_async",
            side_effect=RuntimeError("LLM Call Failed!"),
        ) as mock_process_tasks,
        patch(
            "src.cj_essay_assessment.main.record_comparisons_and_update_scores",
        ) as mock_record_update,
    ):
        mock_db_handler_instance = AsyncMock()
        mock_db_handler_instance.create_tables = AsyncMock()
        mock_db_handler_instance.update_batch_status = AsyncMock()
        # Proper async context manager for session
        mock_session_cm = AsyncMock()
        mock_session = AsyncMock()
        mock_session_cm.__aenter__.return_value = mock_session
        mock_session_cm.__aexit__.return_value = None
        mock_db_handler_instance.session = MagicMock(return_value=mock_session_cm)
        mock_db_handler_class.return_value = mock_db_handler_instance

        mock_settings = create_mock_settings()
        mock_settings.max_pairwise_comparisons = 100
        mock_settings.min_comparisons_for_stability_check = 5
        mock_settings.score_stability_threshold = 0.01
        mock_get_settings.return_value = mock_settings

        mock_essays = [MagicMock(id=i + 1) for i in range(3)]
        mock_process_essays.return_value = mock_essays

        # Simulate generating tasks once
        mock_tasks = [MagicMock() for _ in range(2)]
        mock_generate_tasks.return_value = mock_tasks

        success = await run_comparative_judgment_for_batch(batch_id_to_test)

        assert success is False
        mock_db_handler_instance.create_tables.assert_awaited_once()
        mock_process_essays.assert_awaited_once()
        mock_compute_nlp.assert_awaited_once()
        mock_generate_tasks.assert_awaited_once()
        mock_process_tasks.assert_awaited_once()
        mock_record_update.assert_not_awaited()

        # Assert status updates: NLP -> Ready -> Performing -> ERROR_COMPARISON
        actual_calls = mock_db_handler_instance.update_batch_status.await_args_list
        call_args = [(c.args[1], c.args[2]) for c in actual_calls]

        expected_sequence = [
            (batch_id_to_test, BatchStatusEnum.PROCESSING_NLP),
            (batch_id_to_test, BatchStatusEnum.READY_FOR_COMPARISON),
            (batch_id_to_test, BatchStatusEnum.PERFORMING_COMPARISONS),
            (batch_id_to_test, BatchStatusEnum.ERROR_COMPARISON),
        ]

        try:
            start_index = call_args.index(expected_sequence[0])
            assert (
                call_args[start_index : start_index + len(expected_sequence)]
                == expected_sequence
            )
        except ValueError:
            pytest.fail(
                f"Did not find expected status update sequence {expected_sequence} "
                f"in {call_args}",
            )


@pytest.mark.asyncio
async def test_run_comparative_judgment_no_new_pairs() -> None:
    """Test the main function when there are no new pairs to compare."""
    # Mock all dependencies
    with (
        patch("src.cj_essay_assessment.main.DatabaseHandler") as mock_db_handler_class,
        patch("src.cj_essay_assessment.main.get_settings") as mock_get_settings,
        patch(
            "src.cj_essay_assessment.main.process_essays_for_batch",
        ) as mock_process_essays,
        patch(
            "src.cj_essay_assessment.main.compute_and_store_nlp_stats",
        ) as mock_compute_nlp,
        patch(
            "src.cj_essay_assessment.main.generate_comparison_tasks",
            return_value=[],
        ) as mock_generate_tasks,
    ):
        # Setup mocks
        mock_db_handler = AsyncMock()
        mock_db_handler.create_tables = AsyncMock()
        mock_db_handler.session = MagicMock()
        mock_db_handler_class.return_value = mock_db_handler

        mock_settings = create_mock_settings()
        mock_settings.max_pairwise_comparisons = 100
        mock_get_settings.return_value = mock_settings

        # Setup essay mocks
        mock_essays = [MagicMock() for _ in range(3)]
        mock_process_essays.return_value = mock_essays

        # Run the function
        success = await run_comparative_judgment_for_batch(1)

        # Assert
        assert success is True
        mock_db_handler.create_tables.assert_awaited_once()
        mock_process_essays.assert_awaited_once_with(mock_db_handler, mock_settings, 1)
        mock_compute_nlp.assert_awaited_once_with(
            mock_db_handler,
            mock_settings,
            mock_essays,
        )
        mock_generate_tasks.assert_awaited_once()
        # Should exit loop when no new pairs are available
        assert mock_generate_tasks.await_count == 1


def test_parse_arguments() -> None:
    """Test the argument parser."""
    with patch("sys.argv", ["main.py", "--batch-id", "123", "--log-level", "DEBUG"]):
        args = parse_arguments()
        assert args.batch_id == 123
        assert args.log_level == "DEBUG"

    with patch("sys.argv", ["main.py", "--batch-id", "123"]):
        args = parse_arguments()
        assert args.batch_id == 123
        assert args.log_level == "INFO"  # Default


def test_configure_logging() -> None:
    """Test the logging configuration."""
    with (
        patch("loguru.logger.remove") as mock_remove,
        patch("loguru.logger.add") as mock_add,
        patch("loguru.logger.info") as mock_info,
    ):
        configure_logging("DEBUG")

        # Should remove default logger and add two loggers (stderr and file)
        mock_remove.assert_called_once()
        assert mock_add.call_count == 2
        mock_info.assert_called_once()


@patch("src.cj_essay_assessment.main.parse_arguments")
@patch("src.cj_essay_assessment.main.configure_logging")
@patch(
    "src.cj_essay_assessment.main.run_comparative_judgment_for_batch",
    new_callable=AsyncMock,
)
@patch("asyncio.run")
def test_main_entry_point_success(
    mock_asyncio_run: Mock,
    mock_run_comparative: AsyncMock,
    mock_configure_logging: Mock,
    mock_parse_args: Mock,
) -> None:
    """Test the main entry point when the comparative judgment succeeds."""
    # Arrange parseArguments and return values
    mock_args = MagicMock()
    mock_args.batch_id = 123
    mock_args.log_level = "INFO"
    mock_parse_args.return_value = mock_args

    # Run comparative judgment returns True
    async def async_true(*args, **kwargs):
        return True

    mock_run_comparative.side_effect = async_true

    # Make asyncio.run await the coroutine
    def fake_run(coro: Coroutine[Any, Any, bool]) -> bool:
        return asyncio.get_event_loop().run_until_complete(coro)

    mock_asyncio_run.side_effect = fake_run
    # Act
    exit_code = main_entry_point()
    # Assert
    assert exit_code == 0
    mock_parse_args.assert_called_once()
    mock_configure_logging.assert_called_once_with("INFO")
    mock_asyncio_run.assert_called_once()
    mock_run_comparative.assert_awaited_once_with(mock_args.batch_id)


@patch("src.cj_essay_assessment.main.parse_arguments")
@patch("src.cj_essay_assessment.main.configure_logging")
@patch(
    "src.cj_essay_assessment.main.run_comparative_judgment_for_batch",
    new_callable=AsyncMock,
)
def test_main_entry_point_failure(
    mock_run_comparative_judgment: AsyncMock,
    mock_configure_logging: MagicMock,
    mock_parse_args: MagicMock,
) -> None:
    """Test main entry point handles failure from run_comparative_judgment."""
    # Arrange
    mock_args = MagicMock()
    mock_args.batch_id = 123
    mock_parse_args.return_value = mock_args

    # Ensure the coroutine returns False so main_entry_point exits with code 1
    async def async_false(*args, **kwargs):
        return False

    mock_run_comparative_judgment.side_effect = async_false
    # Act
    exit_code = main_entry_point()
    # Assert
    assert exit_code == 1
    mock_configure_logging.assert_called_once()
    mock_parse_args.assert_called_once()
    # The coroutine should be awaited inside asyncio.run
    mock_run_comparative_judgment.assert_awaited_once_with(
        mock_parse_args.return_value.batch_id,
    )


@patch("src.cj_essay_assessment.main.parse_arguments")
@patch("src.cj_essay_assessment.main.configure_logging")
@patch("asyncio.run", side_effect=Exception("Test error"))
@patch(
    "src.cj_essay_assessment.main.run_comparative_judgment_for_batch",
    new_callable=AsyncMock,
)
def test_main_entry_point_exception(
    mock_run_comparative_judgment: AsyncMock,
    mock_asyncio_run: MagicMock,
    mock_configure_logging: MagicMock,
    mock_parse_args: MagicMock,
) -> None:
    """Test main entry point handles generic exceptions."""
    # Arrange
    mock_args = MagicMock()
    mock_args.batch_id = 456
    mock_parse_args.return_value = mock_args

    # Act
    exit_code = main_entry_point()

    # Assert
    assert exit_code == 1  # Should be 1 as per the except Exception block
    mock_configure_logging.assert_called_once()
    mock_parse_args.assert_called_once()
    mock_asyncio_run.assert_called_once()
    mock_run_comparative_judgment.assert_not_awaited()
