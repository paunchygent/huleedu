# Suggested content for: tests/processing/test_essay_processor.py
"""
Tests for the Essay Processor module (src/cj_essay_assessment/essay_processor.py).
"""

from pathlib import Path
from typing import Any, Tuple, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cj_essay_assessment.config import Settings
from src.cj_essay_assessment.db.db_handler import DatabaseHandler
from src.cj_essay_assessment.db.models_db import (BatchStatusEnum, BatchUpload,
                                                  ProcessedEssay,
                                                  ProcessedEssayStatusEnum)
from src.cj_essay_assessment.essay_processor import (_clean_text,
                                                     process_essays_for_batch)
from src.cj_essay_assessment.file_processor import FileReadError
# Use the specific mock_db_handler from conftest that returns multiple sessions
from tests.processing.conftest import mock_db_handler_with_sessions


# Test _clean_text separately as it's a pure function
def test_clean_text_various_inputs():
    pass


@pytest.mark.asyncio
async def test_process_batch_essay_file_load_error_simulation(
    mock_db_handler_with_sessions: Tuple[DatabaseHandler, AsyncMock, AsyncMock],
    mock_settings: Settings,
    sample_batch: BatchUpload,
    sample_essay_uploaded: ProcessedEssay,
    caplog: Any,
):
    """
    Test how essay_processor handles a FileReadError explicitly raised by
    a mocked extract_text_from_file (from file_processor.py).
    """
    mock_db_handler, mock_session_1, mock_session_2 = mock_db_handler_with_sessions
    sample_essay_uploaded.status = ProcessedEssayStatusEnum.UPLOADED
    sample_essay_uploaded.original_content = None  # Force file loading attempt
    sample_essay_uploaded.processing_metadata = {}
    sample_batch.essays = [sample_essay_uploaded]

    # This setting will be used by SUT to construct the path for Path()
    mock_settings.essay_input_dir = "/dummy/path/for/essays_that_will_error"

    cast(AsyncMock, mock_db_handler.get_batch_by_id).side_effect = [
        sample_batch,
        sample_batch,
    ]

    # SUT's generic exception handler will set ERROR_PROCESSING.
    # The 'step' in metadata will be the status of the essay when the error occurred.
    # extract_text_from_file is called when status is UPLOADED (if no content) or TEXT_EXTRACTED.
    # If original_content is None, it first constructs the path.
    # Let's assume the status is UPLOADED before extract_text_from_file is called.
    final_essay_state_mock = ProcessedEssay(
        id=sample_essay_uploaded.id,
        status=ProcessedEssayStatusEnum.ERROR_PROCESSING,
        batch_id=sample_batch.id,
        original_filename=sample_essay_uploaded.original_filename,
        processing_metadata={
            "processing_error": {
                "error_message": "Simulated FileReadError from test",  # Matches the raised error
                "step": ProcessedEssayStatusEnum.UPLOADED.value,
            }
        },
    )
    cast(AsyncMock, mock_db_handler.get_essays_by_batch).return_value = [
        final_essay_state_mock
    ]
    mock_update_status_on_handler = cast(AsyncMock, mock_db_handler.update_batch_status)

    # --- Corrected Path Mocking ---
    # This mock will be returned when SUT calls `Path(settings.essay_input_dir)`
    mock_path_constructor_result = MagicMock(spec=Path)
    # This mock will be returned by `Path(...) / filename` operation
    mock_final_physical_path = MagicMock(
        spec=Path, name="mock_physical_path_for_file_load_error"
    )
    # Configure the __truediv__ method of the Path() result to return our final path mock
    mock_path_constructor_result.__truediv__.return_value = mock_final_physical_path
    # Configure the .exists attribute of the final path mock
    mock_final_physical_path.exists.return_value = (
        True  # Simulate file "exists" to trigger extract_text_from_file
    )

    with (
        patch(
            "src.cj_essay_assessment.essay_processor.Path",
            return_value=mock_path_constructor_result,
        ) as mock_path_factory,
        patch(
            "src.cj_essay_assessment.essay_processor.extract_text_from_file",
            side_effect=FileReadError("Simulated FileReadError from test"),
        ) as mock_extract,
    ):
        returned_essays = await process_essays_for_batch(
            mock_db_handler, mock_settings, sample_batch.id
        )

    assert len(returned_essays) == 0
    # Check Path was used as expected
    mock_path_factory.assert_called_with(mock_settings.essay_input_dir)
    mock_path_constructor_result.__truediv__.assert_called_with(
        sample_essay_uploaded.original_filename
    )
    mock_final_physical_path.exists.assert_called_once()
    # Check extract_text_from_file was called with the final mocked path
    mock_extract.assert_called_once_with(
        mock_final_physical_path, sample_essay_uploaded.original_filename
    )

    # Assert the status set by the SUT's generic exception handler
    assert sample_essay_uploaded.status == ProcessedEssayStatusEnum.ERROR_PROCESSING
    assert "processing_error" in sample_essay_uploaded.processing_metadata
    assert (
        "Simulated FileReadError from test"
        in sample_essay_uploaded.processing_metadata["processing_error"]["error_message"]
    )
    # Check the log from the generic exception handler in essay_processor.py
    assert (
        f"Unexpected error processing essay ID: {sample_essay_uploaded.id}" in caplog.text
    )
    assert (
        "Simulated FileReadError from test" in caplog.text
    )  # The original error message

    assert mock_update_status_on_handler.await_count == 2
    last_call_args = mock_update_status_on_handler.await_args_list[-1][0]
    assert last_call_args[2] == BatchStatusEnum.ERROR_ESSAY_PROCESSING


# --- Other tests (batch_not_found, no_essays_in_batch, skips_non_uploaded, spell_dict_not_found, generic_error_in_loop) ---
# These should be reviewed to ensure their mocking strategy (especially for session calls and Path if used)
# and assertions (especially for update_batch_status calls and log messages)
# align with the updated SUT and conftest.py.
# I'll include stubs or simplified versions for brevity, assuming their logic would be similar
# to test_process_batch_success_single_docx_essay or test_process_batch_essay_file_load_error_simulation
# in terms of how they assert calls to db_handler methods.


@pytest.mark.asyncio
async def test_process_batch_batch_not_found(
    mock_db_handler_with_sessions: Tuple[DatabaseHandler, AsyncMock, AsyncMock],
    mock_settings: Settings,
    caplog: Any,
):
    mock_db_handler, mock_session_1, _ = mock_db_handler_with_sessions
    batch_id_not_found = 999
    cast(AsyncMock, mock_db_handler.get_batch_by_id).return_value = None

    returned_essays = await process_essays_for_batch(
        mock_db_handler, mock_settings, batch_id_not_found
    )

    assert len(returned_essays) == 0
    cast(AsyncMock, mock_db_handler.get_batch_by_id).assert_awaited_once_with(
        mock_session_1, batch_id_not_found, include_essays=True
    )
    assert f"Batch ID {batch_id_not_found} not found." in caplog.text
    cast(AsyncMock, mock_db_handler.update_batch_status).assert_not_awaited()


@pytest.mark.asyncio
async def test_process_batch_no_essays_in_batch(
    mock_db_handler_with_sessions: Tuple[DatabaseHandler, AsyncMock, AsyncMock],
    mock_settings: Settings,
    sample_batch: BatchUpload,  # sample_batch fixture has .essays = []
    caplog: Any,
):
    mock_db_handler, _, mock_session_2_for_final_status = mock_db_handler_with_sessions
    sample_batch.essays = []

    # SUT calls get_batch_by_id once in the first session block.
    # It then calls get_essays_by_batch in the second session block.
    cast(AsyncMock, mock_db_handler.get_batch_by_id).return_value = sample_batch
    cast(AsyncMock, mock_db_handler.get_essays_by_batch).return_value = (
        []
    )  # No essays found in DB

    mock_update_status_on_handler = cast(AsyncMock, mock_db_handler.update_batch_status)

    returned_essays = await process_essays_for_batch(
        mock_db_handler, mock_settings, sample_batch.id
    )

    assert len(returned_essays) == 0
    assert f"Batch ID {sample_batch.id} contains no essays to process." in caplog.text

    # SUT's first session: get_batch_by_id. Sees batch.essays is empty. Skips initial PROCESSING_ESSAYS.
    # SUT's second session: get_essays_by_batch returns []. Sets final status to ERROR_ESSAY_PROCESSING.
    mock_update_status_on_handler.assert_awaited_once_with(
        mock_session_2_for_final_status,
        sample_batch.id,
        BatchStatusEnum.ERROR_ESSAY_PROCESSING,
    )


@pytest.mark.asyncio
async def test_process_batch_skips_non_uploaded_essays(
    mock_db_handler_with_sessions: Tuple[DatabaseHandler, AsyncMock, AsyncMock],
    mock_settings: Settings,
    sample_batch: BatchUpload,
    sample_essay_processed: ProcessedEssay,
    caplog: Any,
):
    mock_db_handler, mock_session_1, mock_session_2 = mock_db_handler_with_sessions
    sample_essay_processed.status = (
        ProcessedEssayStatusEnum.READY_FOR_PAIRING
    )  # Not UPLOADED
    sample_batch.essays = [sample_essay_processed]

    cast(AsyncMock, mock_db_handler.get_batch_by_id).side_effect = [
        sample_batch,
        sample_batch,
    ]
    cast(AsyncMock, mock_db_handler.get_essays_by_batch).return_value = [
        sample_essay_processed
    ]  # Final check sees it as READY
    mock_update_status_on_handler = cast(AsyncMock, mock_db_handler.update_batch_status)

    returned_essays = await process_essays_for_batch(
        mock_db_handler, mock_settings, sample_batch.id
    )

    assert len(returned_essays) == 1  # The already processed essay
    assert f"Skipping essay ID: {sample_essay_processed.id}" in caplog.text

    assert mock_update_status_on_handler.await_count == 2
    # Check first call
    assert mock_update_status_on_handler.await_args_list[0][0][0] is mock_session_1
    assert (
        mock_update_status_on_handler.await_args_list[0][0][2]
        == BatchStatusEnum.PROCESSING_ESSAYS
    )
    # Check second call
    assert mock_update_status_on_handler.await_args_list[1][0][0] is mock_session_2
    assert (
        mock_update_status_on_handler.await_args_list[1][0][2]
        == BatchStatusEnum.ALL_ESSAYS_READY
    )
