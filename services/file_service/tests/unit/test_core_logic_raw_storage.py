"""
Unit tests for File Service core logic raw storage workflow.

Tests the pre-emptive raw file storage implementation in process_single_file_upload,
ensuring raw blob is stored first before any processing occurs.
"""

from __future__ import annotations

import uuid
from typing import Any, NoReturn
from unittest.mock import AsyncMock

import pytest
from common_core.domain_enums import ContentType
from common_core.error_enums import FileValidationErrorCode
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from common_core.status_enums import ProcessingStatus
from huleedu_service_libs.error_handling.file_validation_factories import (
    raise_content_too_short,
    raise_text_extraction_failed,
)

from services.file_service.core_logic import process_single_file_upload


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
    content_validator.validate_content.return_value = None  # No exception means success
    content_client.store_content.side_effect = ["raw_storage_id_123", "text_storage_id_456"]

    # Act
    file_upload_id = str(uuid.uuid4())
    result = await process_single_file_upload(
        batch_id=batch_id,
        file_upload_id=file_upload_id,
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
    # Note: correlation_id is auto-generated, so we verify the call was made
    text_extractor.extract_text.assert_called_once()
    # Verify the first two arguments are file_content and file_name
    call_args = text_extractor.extract_text.call_args[0]
    assert call_args[0] == file_content
    assert call_args[1] == file_name
    assert len(call_args) == 3  # file_content + file_name + correlation_id

    # Result should contain both storage IDs
    assert result["status"] == ProcessingStatus.COMPLETED.value
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

    # Configure text extraction to raise proper HuleEduError
    def mock_extraction_failure(*args: Any, **kwargs: Any) -> NoReturn:
        raise_text_extraction_failed(
            service="file_service",
            operation="extract_text",
            file_name=file_name,
            message="Extraction failed",
            correlation_id=correlation_id,
        )

    text_extractor.extract_text.side_effect = mock_extraction_failure

    # Act
    file_upload_id = str(uuid.uuid4())
    result = await process_single_file_upload(
        batch_id=batch_id,
        file_upload_id=file_upload_id,
        file_content=file_content,
        file_name=file_name,
        main_correlation_id=correlation_id,
        text_extractor=text_extractor,
        content_validator=content_validator,
        content_client=content_client,
        event_publisher=event_publisher,
    )

    # Assert - Raw storage happened first
    # Note: store_content now includes correlation_id as third parameter
    content_client.store_content.assert_called_once()
    # Verify the call arguments
    call_args = content_client.store_content.call_args[0]
    assert call_args[0] == file_content  # content_bytes
    assert call_args[1] == ContentType.RAW_UPLOAD_BLOB  # content_type
    assert len(call_args) == 3  # content_bytes + content_type + correlation_id

    # Validation failure event published with raw_file_storage_id
    event_publisher.publish_essay_validation_failed.assert_called_once()
    published_event = event_publisher.publish_essay_validation_failed.call_args[0][0]

    assert isinstance(published_event, EssayValidationFailedV1)
    assert published_event.file_upload_id == file_upload_id
    assert published_event.entity_id == batch_id
    assert published_event.original_file_name == file_name
    assert published_event.raw_file_storage_id == "raw_storage_id_123"
    assert published_event.validation_error_code == FileValidationErrorCode.TEXT_EXTRACTION_FAILED

    # Result includes raw storage ID even on failure
    assert result["status"] == ProcessingStatus.FAILED.value
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

    def mock_validation_failure(text: str, file_name: str, correlation_id: uuid.UUID) -> None:
        raise_content_too_short(
            service="file_service",
            operation="validate_content",
            file_name=file_name,
            min_length=50,
            actual_length=len(text),
            correlation_id=correlation_id,
        )

    content_validator.validate_content.side_effect = mock_validation_failure

    # Act
    file_upload_id = str(uuid.uuid4())
    result = await process_single_file_upload(
        batch_id=batch_id,
        file_upload_id=file_upload_id,
        file_content=file_content,
        file_name=file_name,
        main_correlation_id=correlation_id,
        text_extractor=text_extractor,
        content_validator=content_validator,
        content_client=content_client,
        event_publisher=event_publisher,
    )

    # Assert - Raw storage happened first
    # Note: store_content now includes correlation_id as third parameter
    content_client.store_content.assert_called_once()
    # Verify the call arguments
    call_args = content_client.store_content.call_args[0]
    assert call_args[0] == file_content  # content_bytes
    assert call_args[1] == ContentType.RAW_UPLOAD_BLOB  # content_type
    assert len(call_args) == 3  # content_bytes + content_type + correlation_id

    # Validation failure event published with raw_file_storage_id
    event_publisher.publish_essay_validation_failed.assert_called_once()
    published_event = event_publisher.publish_essay_validation_failed.call_args[0][0]

    assert isinstance(published_event, EssayValidationFailedV1)
    assert published_event.file_upload_id == file_upload_id
    assert published_event.entity_id == batch_id
    assert published_event.original_file_name == file_name
    assert published_event.raw_file_storage_id == "raw_storage_id_123"
    assert published_event.validation_error_code == FileValidationErrorCode.CONTENT_TOO_SHORT

    # Result includes raw storage ID
    assert result["status"] == ProcessingStatus.FAILED.value
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
    content_validator.validate_content.return_value = None  # No exception means success
    content_client.store_content.side_effect = ["raw_storage_id_123", "text_storage_id_456"]

    # Act
    file_upload_id = str(uuid.uuid4())
    await process_single_file_upload(
        batch_id=batch_id,
        file_upload_id=file_upload_id,
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
    assert published_event.file_upload_id == file_upload_id
    assert published_event.entity_id == batch_id
    assert published_event.original_file_name == file_name
    assert published_event.raw_file_storage_id == "raw_storage_id_123"
    assert published_event.text_storage_id == "text_storage_id_456"
