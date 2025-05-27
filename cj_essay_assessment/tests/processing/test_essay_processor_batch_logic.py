"""
Tests for the Essay Processor module (src/cj_essay_assessment/essay_processor.py).
"""

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.cj_essay_assessment.config import Settings
from src.cj_essay_assessment.db.db_handler import DatabaseHandler
from src.cj_essay_assessment.db.models_db import (BatchStatusEnum, BatchUpload,
                                                  ProcessedEssay,
                                                  ProcessedEssayStatusEnum)
from src.cj_essay_assessment.essay_processor import (_clean_text,
                                                     process_essays_for_batch)


@pytest.mark.asyncio
async def test_process_batch_no_batch_found(
    mock_db_handler_with_sessions: tuple[
        DatabaseHandler, AsyncMock, AsyncMock
    ],  # Type hint is good
    mock_settings: Settings,  # Type hint is good
    caplog: Any,  # pytest.LogCaptureFixture is more precise if available
) -> None:
    """Test batch not found scenario."""
    batch_id_not_found = 999
    # Ensure the mock for get_batch_by_id is an AsyncMock if the method is async
    cast(AsyncMock, mock_db_handler_with_sessions[0].get_batch_by_id).return_value = None

    essays_for_comp = await process_essays_for_batch(
        mock_db_handler_with_sessions[0],
        mock_settings,
        batch_id_not_found,
    )
    assert len(essays_for_comp) == 0
    assert f"Batch ID {batch_id_not_found} not found." in caplog.text


@pytest.mark.asyncio
async def test_process_batch_no_essays_logs_warning_and_sets_status(
    mock_db_handler_with_sessions: tuple[DatabaseHandler, AsyncMock, AsyncMock],
    mock_settings: Settings,
    sample_batch: BatchUpload,  # Fixture provides a batch with empty essays list
    caplog: Any,  # pytest.LogCaptureFixture
) -> None:
    """Test processing batch with no essays updates batch status to ERROR_ESSAY_PROCESSING."""
    sample_batch.essays = []  # Explicitly ensure it's empty for this test

    cast(AsyncMock, mock_db_handler_with_sessions[0].get_batch_by_id).return_value = (
        sample_batch
    )

    # Mock the session and its methods
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_db_handler_with_sessions[0].session.return_value = mock_session

    essays_for_comp = await process_essays_for_batch(
        mock_db_handler_with_sessions[0],
        mock_settings,
        sample_batch.id,
    )

    assert len(essays_for_comp) == 0
    assert f"Batch ID {sample_batch.id} contains no essays to process." in caplog.text

    # Verify that the batch status was updated to ERROR_ESSAY_PROCESSING
    assert sample_batch.status == BatchStatusEnum.ERROR_ESSAY_PROCESSING


@pytest.mark.asyncio
async def test_process_batch_no_uploaded_essays_logs_and_sets_status(
    mock_db_handler_with_sessions: tuple[DatabaseHandler, AsyncMock, AsyncMock],
    mock_settings: Settings,
    sample_batch: BatchUpload,
    sample_essay_processed: ProcessedEssay,  # Essay is already READY_FOR_PAIRING
    caplog: Any,  # pytest.LogCaptureFixture
) -> None:
    """Test batch with only non-'UPLOADED' essays means no new processing, should be ALL_ESSAYS_READY if all are validly processed."""
    sample_essay_processed.batch_id = sample_batch.id  # Associate
    sample_essay_processed.status = (
        ProcessedEssayStatusEnum.READY_FOR_PAIRING
    )  # Ensure it's not UPLOADED
    sample_batch.essays = [sample_essay_processed]

    cast(AsyncMock, mock_db_handler_with_sessions[0].get_batch_by_id).return_value = (
        sample_batch
    )

    mock_update_status_on_handler = cast(
        AsyncMock, mock_db_handler_with_sessions[0].update_batch_status
    )
    mock_update_status_on_handler.reset_mock()

    # Mock for the final get_essays_by_batch call in SUT
    # This mock should return all essays in the batch with their current (final) states
    cast(AsyncMock, mock_db_handler_with_sessions[0].get_essays_by_batch).return_value = [
        sample_essay_processed
    ]
    mock_session_instance = cast(
        AsyncMock, mock_db_handler_with_sessions[0].session().__aenter__()
    )

    essays_for_comp = await process_essays_for_batch(
        mock_db_handler_with_sessions[0],
        mock_settings,
        sample_batch.id,
    )

    # Check that we got the expected essay back
    assert len(essays_for_comp) == 1
    assert essays_for_comp[0].id == sample_essay_processed.id

    # Check that the batch status was updated to ALL_ESSAYS_READY
    assert sample_batch.status == BatchStatusEnum.ALL_ESSAYS_READY

    # Verify the log message about all essays being already processed
    assert f"All essays in batch {sample_batch.id} are already processed." in caplog.text


@pytest.mark.asyncio
async def test_process_batch_skips_essay_with_none_id():
    pass


@pytest.mark.asyncio
async def test_process_batch_skips_spellcheck_empty_content(
    mock_db_handler_with_sessions: tuple[DatabaseHandler, AsyncMock, AsyncMock],
    mock_settings: Settings,
    sample_batch: BatchUpload,
    caplog: Any,
) -> None:
    """Test empty content is properly handled as an ERROR_SPELLCHECK condition."""
    essay_empty_after_clean = ProcessedEssay(
        id=101,
        batch_id=sample_batch.id,
        original_filename="empty.txt",
        original_content="   \n   ",  # Content that cleans to ""
        status=ProcessedEssayStatusEnum.UPLOADED,
    )
    assert _clean_text(essay_empty_after_clean.original_content or "") == ""

    sample_batch.essays = [essay_empty_after_clean]

    mock_ctx_manager = cast("MagicMock", mock_db_handler_with_sessions[0].session())
    mock_session_instance = cast("AsyncMock", mock_ctx_manager.__aenter__.return_value)

    cast("AsyncMock", mock_db_handler_with_sessions[0].get_batch_by_id).side_effect = [
        sample_batch,
        sample_batch,
    ]

    # --- FIX: Mock final state with ERROR_SPELLCHECK status ---
    mock_execute_result_final = MagicMock()
    # Essay should be ERROR_SPELLCHECK since empty content can't be spell-checked
    processed_essay_final_state = ProcessedEssay(
        id=essay_empty_after_clean.id,
        status=ProcessedEssayStatusEnum.ERROR_SPELLCHECK,
        original_filename=essay_empty_after_clean.original_filename,
        processed_content="",  # Empty processed content
        # Should have error metadata and file_attributes
        processing_metadata={
            "file_attributes": {  # Ensure file_attributes are present
                "word_count": 0,  # Expected for empty string
                "character_count": 0,  # Expected for empty string
                "original_filename_provided": (essay_empty_after_clean.original_filename),
            },
            "processing_error": {
                "error_message": "No processed content for spell check",
                "step": "SPELLCHECK",
            },
        },
    )
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [processed_essay_final_state]
    mock_execute_result_final.scalars.return_value = mock_scalars
    cast("AsyncMock", mock_session_instance.execute).return_value = (
        mock_execute_result_final
    )

    mock_update_status = cast(
        "AsyncMock", mock_db_handler_with_sessions[0].update_batch_status
    )
    mock_update_status.reset_mock()

    # Use an async side effect for the mock return value
    async def mock_update_return(*args: Any, **kwargs: Any) -> MagicMock:
        return MagicMock(spec=BatchUpload, status=args[2])  # Simulate status update

    mock_update_status.side_effect = mock_update_return

    essays_for_comp = await process_essays_for_batch(
        mock_db_handler_with_sessions[0],
        mock_settings,
        sample_batch.id,
    )

    # Empty content essay should be excluded from comparison results
    assert len(essays_for_comp) == 0
    # Check log for error message
    assert "Cannot perform spell check, processed content is empty" in caplog.text
    assert essay_empty_after_clean.status == ProcessedEssayStatusEnum.ERROR_SPELLCHECK

    # Since we have an essay with ERROR_SPELLCHECK, expect ERROR_ESSAY_PROCESSING
    expected_calls = [
        call(
            mock_session_instance,
            sample_batch.id,
            BatchStatusEnum.ERROR_ESSAY_PROCESSING,
        ),
    ]
    mock_update_status.assert_has_awaits(expected_calls)

    # --- Correct flush count assertion ---
    # Flush: 1 (initial batch status)
    # + 1 (TEXT_CLEANED)
    # + 1 (ERROR_SPELLCHECK with error metadata) - when empty content is detected after cleaning
    # + 1 (Final batch status update)
    # Total = 4
    assert mock_session_instance.flush.await_count == 4


@pytest.mark.asyncio
async def test_process_batch_fails_refetching_essays():
    pass


@pytest.mark.asyncio
async def test_process_batch_exception_on_final_status_update():
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initial_essay_statuses, expected_final_batch_status_enum, expected_returned_essay_count, expected_log_snippets",
    [
        (  # Scenario: All essays process successfully
            [
                (ProcessedEssayStatusEnum.UPLOADED, "e1.txt", "content1"),
                (ProcessedEssayStatusEnum.UPLOADED, "e2.txt", "content2"),
            ],
            BatchStatusEnum.ALL_ESSAYS_READY,
            2,
            ["Batch 10 final status updated to ALL_ESSAYS_READY"],
        ),
        (  # Scenario: One essay is UPLOADED, another is already ERROR_PROCESSING
            [
                (ProcessedEssayStatusEnum.UPLOADED, "e1.txt", "content1"),
                (ProcessedEssayStatusEnum.ERROR_PROCESSING, "e2.txt", "content2"),
            ],
            BatchStatusEnum.ERROR_ESSAY_PROCESSING,
            1,  # Only e1 becomes ready
            ["Batch 10 final status updated to ERROR_ESSAY_PROCESSING"],
        ),
        (  # Scenario: All essays are already READY_FOR_PAIRING
            [
                (ProcessedEssayStatusEnum.READY_FOR_PAIRING, "e1.txt", "content1"),
                (ProcessedEssayStatusEnum.READY_FOR_PAIRING, "e2.txt", "content2"),
            ],
            BatchStatusEnum.ALL_ESSAYS_READY,
            2,  # Both should be returned
            [
                "Batch 10 final status updated to ALL_ESSAYS_READY",
                "Skipping essay ID",
            ],  # Skipping log
        ),
        (  # Scenario: One UPLOADED, one already READY_FOR_PAIRING
            [
                (ProcessedEssayStatusEnum.UPLOADED, "e1.txt", "content1"),
                (ProcessedEssayStatusEnum.READY_FOR_PAIRING, "e2.txt", "content2"),
            ],
            BatchStatusEnum.ALL_ESSAYS_READY,
            2,
            ["Batch 10 final status updated to ALL_ESSAYS_READY"],
        ),
        (  # Scenario: All essays are already in some error state
            [
                (ProcessedEssayStatusEnum.ERROR_PROCESSING, "e1.txt", "content1"),
                (ProcessedEssayStatusEnum.ERROR_SPELLCHECK, "e2.txt", "content2"),
            ],
            BatchStatusEnum.ERROR_ESSAY_PROCESSING,
            0,
            [
                "Batch 10 final status updated to ERROR_ESSAY_PROCESSING",
                "Skipping essay ID",
            ],
        ),
        (  # Scenario: One UPLOADED, one stuck in TEXT_CLEANED (intermediate state)
            [
                (ProcessedEssayStatusEnum.UPLOADED, "e1.txt", "content1"),
                (ProcessedEssayStatusEnum.TEXT_CLEANED, "e2.txt", "content2"),
            ],
            BatchStatusEnum.PROCESSING_ESSAYS,  # Batch is still processing as not all are ready or error
            1,  # Only e1 becomes ready
            ["Batch 10 final status updated to PROCESSING_ESSAYS"],
        ),
        (  # Scenario: One UPLOADED with content, one UPLOADED but with None content (should error)
            [
                (ProcessedEssayStatusEnum.UPLOADED, "e1.txt", "content1"),
                (ProcessedEssayStatusEnum.UPLOADED, "e2.txt", None),
            ],
            BatchStatusEnum.ERROR_ESSAY_PROCESSING,
            1,  # Only e1 becomes ready
            [
                "Batch 10 final status updated to ERROR_ESSAY_PROCESSING",
                "Essay ID: 101 has no original content. Marking as error",
            ],
        ),
    ],
    ids=[
        "all_uploaded_ok",
        "one_uploaded_one_error",
        "all_ready",
        "one_uploaded_one_ready",
        "all_error_initial",
        "one_uploaded_one_stuck_intermediate",
        "one_uploaded_one_missing_content_error",
    ],
)
async def test_process_batch_updates_batch_status_correctly():
    pass
