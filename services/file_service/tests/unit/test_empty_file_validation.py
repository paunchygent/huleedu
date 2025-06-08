"""
Test empty file validation using the elegant implementation.

This test validates that empty files are properly handled through content validation
rather than being treated as text extraction failures.
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from common_core.events.file_events import EssayValidationFailedV1
from services.file_service.core_logic import process_single_file_upload
from services.file_service.validation_models import ValidationResult


@pytest.mark.asyncio
async def test_empty_file_uses_content_validation() -> None:
    """
    Test that empty files are handled by content validation with proper EMPTY_CONTENT error code.

    This ensures the elegant separation of concerns:
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
    content_validator.validate_content.return_value = ValidationResult(
        is_valid=False,
        error_code="EMPTY_CONTENT",
        error_message="File 'empty_essay.txt' contains no readable text content."
    )

    content_client = AsyncMock()
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
    text_extractor.extract_text.assert_called_once_with(empty_file_content, file_name)

    # Assert - Content validation was called with empty string
    content_validator.validate_content.assert_called_once_with("", file_name)

    # Assert - Content storage was NOT called (validation failed)
    content_client.store_content.assert_not_called()

    # Assert - Validation failure event was published with correct error code
    event_publisher.publish_essay_validation_failed.assert_called_once()
    published_event = event_publisher.publish_essay_validation_failed.call_args[0][0]

    assert isinstance(published_event, EssayValidationFailedV1)
    assert published_event.validation_error_code == "EMPTY_CONTENT"
    assert published_event.validation_error_message == (
        "File 'empty_essay.txt' contains no readable text content."
    )
    assert published_event.batch_id == batch_id
    assert published_event.original_file_name == file_name

    # Assert - Success event was NOT published
    event_publisher.publish_essay_content_provisioned.assert_not_called()

    # Assert - Correct return status
    assert result["status"] == "content_validation_failed"
    assert result["error_code"] == "EMPTY_CONTENT"
    assert result["file_name"] == file_name


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
    text_extractor.extract_text.assert_called_once_with(file_content, file_name)

    # Assert - Content validation was NOT called (extraction failed)
    content_validator.validate_content.assert_not_called()

    # Assert - Technical failure event was published
    event_publisher.publish_essay_validation_failed.assert_called_once()
    published_event = event_publisher.publish_essay_validation_failed.call_args[0][0]

    assert published_event.validation_error_code == "TEXT_EXTRACTION_FAILED"
    assert "Technical text extraction failure" in published_event.validation_error_message
    assert "File format not supported" in published_event.validation_error_message

    # Assert - Correct return status
    assert result["status"] == "extraction_failed"
    assert result["file_name"] == file_name


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
    content_validator.validate_content.return_value = ValidationResult(
        is_valid=False,
        error_code="CONTENT_TOO_SHORT",
        error_message=(
            "File 'too_short.txt' contains only 2 characters. "
            "Essays must contain at least 50 characters."
        )
    )

    content_client = AsyncMock()
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
    content_validator.validate_content.assert_called_once_with("Hi", file_name)

    # Assert - Correct validation failure event
    published_event = event_publisher.publish_essay_validation_failed.call_args[0][0]
    assert published_event.validation_error_code == "CONTENT_TOO_SHORT"

    # Assert - Correct return status
    assert result["status"] == "content_validation_failed"
    assert result["error_code"] == "CONTENT_TOO_SHORT"
