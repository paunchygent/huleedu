"""
Test empty file validation using the elegant implementation.

This test validates that empty files are properly handled through content validation
rather than being treated as text extraction failures.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from common_core.domain_enums import ContentType
from common_core.error_enums import FileValidationErrorCode
from common_core.events.file_events import EssayValidationFailedV1
from common_core.status_enums import ProcessingStatus
from huleedu_service_libs.error_handling.file_validation_factories import (
    raise_content_too_short,
    raise_empty_content_error,
)

from services.file_service.core_logic import process_single_file_upload


@pytest.mark.asyncio
async def test_empty_file_uses_content_validation() -> None:
    """
    Test that empty files are handled by content validation with proper EMPTY_CONTENT error code.

    This ensures the elegant separation of concerns:
    - Raw storage happens first (pre-emptive storage)
    - Text extraction succeeds (returns empty string)
    - Content validation fails with EMPTY_CONTENT error code
    """
    # Arrange
    batch_id = "test-batch-123"
    empty_file_content = b""  # Truly empty file
    file_name = "empty_essay.txt"
    correlation_id = uuid.uuid4()

    # Mock dependencies
    text_extractor = AsyncMock()
    text_extractor.extract_text.return_value = ""  # Empty string (successful extraction)

    content_validator = AsyncMock()

    def mock_empty_validation(text: str, file_name: str, correlation_id: uuid.UUID) -> None:
        raise_empty_content_error(
            service="file_service",
            operation="validate_content",
            file_name=file_name,
            correlation_id=correlation_id,
        )

    content_validator.validate_content.side_effect = mock_empty_validation

    content_client = AsyncMock()
    content_client.store_content.return_value = "raw_storage_empty_12345"  # Proper string return

    event_publisher = AsyncMock()

    # Act
    result = await process_single_file_upload(
        batch_id=batch_id,
        file_content=empty_file_content,
        file_name=file_name,
        main_correlation_id=correlation_id,
        text_extractor=text_extractor,
        content_validator=content_validator,
        content_client=content_client,
        event_publisher=event_publisher,
    )

    # Assert - Text extraction was called and succeeded
    # Note: correlation_id is auto-generated, so we verify the call was made
    text_extractor.extract_text.assert_called_once()
    # Verify the first two arguments are file_content and file_name
    call_args = text_extractor.extract_text.call_args[0]
    assert call_args[0] == empty_file_content
    assert call_args[1] == file_name
    assert len(call_args) == 3  # file_content + file_name + correlation_id

    # Assert - Content validation was called with empty string
    # Note: correlation_id is auto-generated, so we verify the call was made
    content_validator.validate_content.assert_called_once()
    # Verify the first two arguments are text and file_name
    call_args = content_validator.validate_content.call_args[0]
    assert call_args[0] == ""
    assert call_args[1] == file_name
    assert len(call_args) == 3  # text + file_name + correlation_id

    # Assert - Raw storage was called (NEW BEHAVIOR)
    # Note: store_content now includes correlation_id as third parameter
    assert content_client.store_content.call_count == 1
    call_args = content_client.store_content.call_args[0]
    assert call_args[0] == empty_file_content  # content_bytes
    assert call_args[1] == ContentType.RAW_UPLOAD_BLOB  # content_type
    assert len(call_args) == 3  # content_bytes + content_type + correlation_id

    # Assert - Validation failure event was published with correct error code
    event_publisher.publish_essay_validation_failed.assert_called_once()
    published_event = event_publisher.publish_essay_validation_failed.call_args[0][0]

    assert isinstance(published_event, EssayValidationFailedV1)
    assert published_event.validation_error_code == FileValidationErrorCode.EMPTY_CONTENT
    # Updated to match HuleEduError factory message format
    assert published_event.validation_error_message == (
        "File 'empty_essay.txt' has empty content"
    )
    assert published_event.batch_id == batch_id
    assert published_event.original_file_name == file_name
    assert published_event.raw_file_storage_id == "raw_storage_empty_12345"  # Raw storage ID

    # Assert - Success event was NOT published
    event_publisher.publish_essay_content_provisioned.assert_not_called()

    # Assert - Correct return status
    assert result["status"] == ProcessingStatus.FAILED.value
    assert result["error_code"] == FileValidationErrorCode.EMPTY_CONTENT
    assert result["file_name"] == file_name
    assert result["raw_file_storage_id"] == "raw_storage_empty_12345"


@pytest.mark.asyncio
async def test_text_extraction_failure_vs_empty_content() -> None:
    """
    Test that true text extraction failures are distinguished from empty content.

    This verifies:
    - Technical extraction failures get TEXT_EXTRACTION_FAILED error code
    - Empty content gets EMPTY_CONTENT error code
    """
    # Arrange
    batch_id = "test-batch-456"
    file_content = b"corrupted_file_content"
    file_name = "corrupted.txt"
    correlation_id = uuid.uuid4()

    # Mock text extraction failure (technical issue)
    text_extractor = AsyncMock()
    text_extractor.extract_text.side_effect = Exception("File format not supported")

    content_validator = AsyncMock()

    content_client = AsyncMock()
    content_client.store_content.return_value = "raw_storage_corrupted_67890"  # String return

    event_publisher = AsyncMock()

    # Act
    result = await process_single_file_upload(
        batch_id=batch_id,
        file_content=file_content,
        file_name=file_name,
        main_correlation_id=correlation_id,
        text_extractor=text_extractor,
        content_validator=content_validator,
        content_client=content_client,
        event_publisher=event_publisher,
    )

    # Assert - Text extraction was attempted
    # Note: correlation_id is auto-generated, so we verify the call was made
    text_extractor.extract_text.assert_called_once()
    # Verify the first two arguments are file_content and file_name
    call_args = text_extractor.extract_text.call_args[0]
    assert call_args[0] == file_content
    assert call_args[1] == file_name
    assert len(call_args) == 3  # file_content + file_name + correlation_id

    # Assert - Raw storage was called (NEW BEHAVIOR - happens before extraction)
    # Note: store_content now includes correlation_id as third parameter
    assert content_client.store_content.call_count == 1
    call_args = content_client.store_content.call_args[0]
    assert call_args[0] == file_content  # content_bytes
    assert call_args[1] == ContentType.RAW_UPLOAD_BLOB  # content_type
    assert len(call_args) == 3  # content_bytes + content_type + correlation_id

    # Assert - Content validation was NOT called (extraction failed)
    content_validator.validate_content.assert_not_called()

    # Assert - Technical failure event was published
    event_publisher.publish_essay_validation_failed.assert_called_once()
    published_event = event_publisher.publish_essay_validation_failed.call_args[0][0]

    assert published_event.validation_error_code == FileValidationErrorCode.TEXT_EXTRACTION_FAILED
    assert "Technical text extraction failure" in published_event.validation_error_message
    assert "File format not supported" in published_event.validation_error_message
    assert published_event.raw_file_storage_id == "raw_storage_corrupted_67890"  # Raw ID

    # Assert - Correct return status
    assert result["status"] == ProcessingStatus.FAILED.value
    assert result["file_name"] == file_name
    assert result["raw_file_storage_id"] == "raw_storage_corrupted_67890"


@pytest.mark.asyncio
async def test_content_too_short_validation() -> None:
    """
    Test that content validation properly handles files that are too short.

    This ensures all content validation rules work through the new architecture.
    """
    # Arrange
    batch_id = "test-batch-789"
    short_file_content = b"Hi"  # Very short content
    file_name = "too_short.txt"
    correlation_id = uuid.uuid4()

    # Mock dependencies
    text_extractor = AsyncMock()
    text_extractor.extract_text.return_value = "Hi"  # Short but not empty

    content_validator = AsyncMock()

    def mock_short_validation(text: str, file_name: str, correlation_id: uuid.UUID) -> None:
        raise_content_too_short(
            service="file_service",
            operation="validate_content",
            file_name=file_name,
            min_length=50,
            actual_length=len(text),
            correlation_id=correlation_id,
        )

    content_validator.validate_content.side_effect = mock_short_validation

    content_client = AsyncMock()
    content_client.store_content.return_value = "raw_storage_short_11111"

    event_publisher = AsyncMock()

    # Act
    result = await process_single_file_upload(
        batch_id=batch_id,
        file_content=short_file_content,
        file_name=file_name,
        main_correlation_id=correlation_id,
        text_extractor=text_extractor,
        content_validator=content_validator,
        content_client=content_client,
        event_publisher=event_publisher,
    )

    # Assert - Both extraction and validation were called
    text_extractor.extract_text.assert_called_once()
    # Note: correlation_id is auto-generated, so we verify the call was made
    content_validator.validate_content.assert_called_once()
    # Verify the first two arguments are text and file_name
    call_args = content_validator.validate_content.call_args[0]
    assert call_args[0] == "Hi"
    assert call_args[1] == file_name
    assert len(call_args) == 3  # text + file_name + correlation_id

    # Assert - Raw storage was called (NEW BEHAVIOR)
    # Note: store_content now includes correlation_id as third parameter
    assert content_client.store_content.call_count == 1
    call_args = content_client.store_content.call_args[0]
    assert call_args[0] == short_file_content  # content_bytes
    assert call_args[1] == ContentType.RAW_UPLOAD_BLOB  # content_type
    assert len(call_args) == 3  # content_bytes + content_type + correlation_id

    # Assert - Correct validation failure event
    event_publisher.publish_essay_validation_failed.assert_called_once()
    published_event = event_publisher.publish_essay_validation_failed.call_args[0][0]
    assert published_event.validation_error_code == FileValidationErrorCode.CONTENT_TOO_SHORT
    assert published_event.raw_file_storage_id == "raw_storage_short_11111"

    # Assert - Correct return status
    assert result["status"] == ProcessingStatus.FAILED.value
    assert result["error_code"] == FileValidationErrorCode.CONTENT_TOO_SHORT
    assert result["raw_file_storage_id"] == "raw_storage_short_11111"
