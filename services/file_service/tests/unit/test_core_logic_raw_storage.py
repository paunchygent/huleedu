"""
Unit tests for File Service core logic raw storage workflow.

Tests the pre-emptive raw file storage implementation in process_single_file_upload,
ensuring raw blob is stored first before any processing occurs.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from common_core.enums import ContentType
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from services.file_service.core_logic import process_single_file_upload
from services.file_service.validation_models import ValidationResult


@pytest.mark.asyncio
async def test_process_single_file_stores_raw_blob_first() -> None:
    """Test that raw file blob is stored BEFORE text extraction occurs."""
    # Arrange
    batch_id = str(uuid.uuid4())
    file_content = b"Test essay content"
    file_name = "test_essay.txt"
    correlation_id = uuid.uuid4()

    # Mock dependencies
    text_extractor = AsyncMock()
    content_validator = AsyncMock()
    content_client = AsyncMock()
    event_publisher = AsyncMock()

    # Configure mocks
    text_extractor.extract_text.return_value = "Test essay content"
    content_validator.validate_content.return_value = ValidationResult(is_valid=True)
    content_client.store_content.side_effect = ["raw_storage_id_123", "text_storage_id_456"]

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

    # Assert - Raw blob stored FIRST
    assert content_client.store_content.call_count == 2
    first_call = content_client.store_content.call_args_list[0]
    second_call = content_client.store_content.call_args_list[1]

    # First call should be raw blob
    assert first_call[0][0] == file_content  # Raw file bytes
    assert first_call[0][1] == ContentType.RAW_UPLOAD_BLOB

    # Second call should be extracted text
    assert second_call[0][0] == b"Test essay content"  # Encoded text
    assert second_call[0][1] == ContentType.EXTRACTED_PLAINTEXT

    # Text extraction should happen AFTER raw storage
    text_extractor.extract_text.assert_called_once_with(file_content, file_name)

    # Result should contain both storage IDs
    assert result["status"] == "processing_success"
    assert result["raw_file_storage_id"] == "raw_storage_id_123"
    assert result["text_storage_id"] == "text_storage_id_456"


@pytest.mark.asyncio
async def test_extraction_failure_includes_raw_storage_id() -> None:
    """Test that extraction failure events include raw_file_storage_id."""
    # Arrange
    batch_id = str(uuid.uuid4())
    file_content = b"Corrupted file content"
    file_name = "corrupted.txt"
    correlation_id = uuid.uuid4()

    # Mock dependencies
    text_extractor = AsyncMock()
    content_validator = AsyncMock()
    content_client = AsyncMock()
    event_publisher = AsyncMock()

    # Configure mocks - extraction fails, but raw storage succeeds
    content_client.store_content.return_value = "raw_storage_id_123"
    text_extractor.extract_text.side_effect = Exception("Extraction failed")

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

    # Assert - Raw storage happened first
    content_client.store_content.assert_called_once_with(file_content, ContentType.RAW_UPLOAD_BLOB)

    # Validation failure event published with raw_file_storage_id
    event_publisher.publish_essay_validation_failed.assert_called_once()
    published_event = event_publisher.publish_essay_validation_failed.call_args[0][0]

    assert isinstance(published_event, EssayValidationFailedV1)
    assert published_event.raw_file_storage_id == "raw_storage_id_123"
    assert published_event.validation_error_code == "TEXT_EXTRACTION_FAILED"

    # Result includes raw storage ID even on failure
    assert result["status"] == "extraction_failed"
    assert result["raw_file_storage_id"] == "raw_storage_id_123"


@pytest.mark.asyncio
async def test_validation_failure_includes_raw_storage_id() -> None:
    """Test that validation failure events include raw_file_storage_id."""
    # Arrange
    batch_id = str(uuid.uuid4())
    file_content = b"Invalid content"
    file_name = "invalid.txt"
    correlation_id = uuid.uuid4()

    # Mock dependencies
    text_extractor = AsyncMock()
    content_validator = AsyncMock()
    content_client = AsyncMock()
    event_publisher = AsyncMock()

    # Configure mocks - validation fails
    content_client.store_content.return_value = "raw_storage_id_123"
    text_extractor.extract_text.return_value = ""  # Empty content
    content_validator.validate_content.return_value = ValidationResult(
        is_valid=False, error_code="CONTENT_TOO_SHORT", error_message="Content is too short",
    )

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

    # Assert - Raw storage happened first
    content_client.store_content.assert_called_once_with(file_content, ContentType.RAW_UPLOAD_BLOB)

    # Validation failure event published with raw_file_storage_id
    event_publisher.publish_essay_validation_failed.assert_called_once()
    published_event = event_publisher.publish_essay_validation_failed.call_args[0][0]

    assert isinstance(published_event, EssayValidationFailedV1)
    assert published_event.raw_file_storage_id == "raw_storage_id_123"
    assert published_event.validation_error_code == "CONTENT_TOO_SHORT"

    # Result includes raw storage ID
    assert result["status"] == "content_validation_failed"
    assert result["raw_file_storage_id"] == "raw_storage_id_123"


@pytest.mark.asyncio
async def test_success_event_includes_both_storage_ids() -> None:
    """Test that success events include both raw_file_storage_id and text_storage_id."""
    # Arrange
    batch_id = str(uuid.uuid4())
    file_content = b"Valid essay content"
    file_name = "valid.txt"
    correlation_id = uuid.uuid4()

    # Mock dependencies
    text_extractor = AsyncMock()
    content_validator = AsyncMock()
    content_client = AsyncMock()
    event_publisher = AsyncMock()

    # Configure mocks for success path
    text_extractor.extract_text.return_value = "Valid essay content"
    content_validator.validate_content.return_value = ValidationResult(is_valid=True)
    content_client.store_content.side_effect = ["raw_storage_id_123", "text_storage_id_456"]

    # Act
    await process_single_file_upload(
        batch_id=batch_id,
        file_content=file_content,
        file_name=file_name,
        main_correlation_id=correlation_id,
        text_extractor=text_extractor,
        content_validator=content_validator,
        content_client=content_client,
        event_publisher=event_publisher,
    )

    # Assert - Success event published with both storage IDs
    event_publisher.publish_essay_content_provisioned.assert_called_once()
    published_event = event_publisher.publish_essay_content_provisioned.call_args[0][0]

    assert isinstance(published_event, EssayContentProvisionedV1)
    assert published_event.raw_file_storage_id == "raw_storage_id_123"
    assert published_event.text_storage_id == "text_storage_id_456"
    assert published_event.batch_id == batch_id
    assert published_event.original_file_name == file_name
