"""
Tests for validation failure workflows in core logic validation integration.

Tests various validation failure scenarios including empty content, content too short,
content too long, and proper event publishing for failure cases.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from common_core.domain_enums import ContentType
from common_core.error_enums import FileValidationErrorCode
from common_core.events.file_events import EssayValidationFailedV1

from services.file_service.core_logic import process_single_file_upload
from services.file_service.tests.unit.core_logic_validation_utils import (
    EMPTY_FILE_CONTENT,
    TEST_BATCH_IDS,
    TEST_FILE_NAMES,
    ZERO_BYTE_CONTENT,
)
from services.file_service.validation_models import FileProcessingStatus, ValidationResult


class TestCoreLogicValidationFailures:
    """Test suite for validation failure scenarios in core logic integration."""

    @pytest.mark.asyncio
    async def test_validation_failure_workflow(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test validation failure workflow with proper event publishing."""
        # Arrange
        batch_id = TEST_BATCH_IDS["validation_failure"]
        file_content = EMPTY_FILE_CONTENT
        file_name = TEST_FILE_NAMES["empty"]
        correlation_id = uuid.uuid4()

        # Configure mocks for new pre-emptive raw storage behavior
        mock_content_client.store_content.return_value = "raw_storage_12345"
        mock_text_extractor.extract_text.return_value = "Short text"

        # Configure validation to fail
        mock_content_validator.validate_content.return_value = ValidationResult(
            is_valid=False,
            error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            error_message="Content length (5 characters) below minimum threshold (50)",
        )

        # Act
        result = await process_single_file_upload(
            batch_id=batch_id,
            file_content=file_content,
            file_name=file_name,
            main_correlation_id=correlation_id,
            text_extractor=mock_text_extractor,
            content_validator=mock_content_validator,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
        )

        # Assert validation failure response
        assert result["file_name"] == file_name
        assert result["status"] == FileProcessingStatus.CONTENT_VALIDATION_FAILED.value
        assert result["error_code"] == FileValidationErrorCode.CONTENT_TOO_SHORT
        assert "5 characters" in result["error_message"]
        assert result["raw_file_storage_id"] == "raw_storage_12345"
        assert "text_storage_id" not in result  # Only raw storage for validation failures

        # Verify text extraction was called
        mock_text_extractor.extract_text.assert_called_once_with(file_content, file_name)

        # Verify validation was called
        mock_content_validator.validate_content.assert_called_once()

        # Verify content storage was called ONCE for raw storage (NEW BEHAVIOR)
        mock_content_client.store_content.assert_called_once_with(
            file_content,
            ContentType.RAW_UPLOAD_BLOB,
        )

        # Verify validation failure event was published
        mock_event_publisher.publish_essay_validation_failed.assert_called_once()
        failure_event_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_event_call[0][0]
        assert isinstance(event_data, EssayValidationFailedV1)
        assert event_data.batch_id == batch_id
        assert event_data.original_file_name == file_name
        assert event_data.validation_error_code == FileValidationErrorCode.CONTENT_TOO_SHORT
        assert event_data.file_size_bytes == len(file_content)
        assert event_data.raw_file_storage_id == "raw_storage_12345"  # NEW: includes raw storage ID

        # Verify success event was NOT published
        mock_event_publisher.publish_essay_content_provisioned.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_content_validation_failure(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling of empty content validation failure."""
        # Arrange
        batch_id = TEST_BATCH_IDS["empty_content"]
        file_content = ZERO_BYTE_CONTENT
        file_name = "empty_file.txt"
        correlation_id = uuid.uuid4()

        # Configure mocks for new pre-emptive raw storage behavior
        mock_content_client.store_content.return_value = "raw_storage_empty_123"
        mock_text_extractor.extract_text.return_value = ""

        mock_content_validator.validate_content.return_value = ValidationResult(
            is_valid=False,
            error_code=FileValidationErrorCode.EMPTY_CONTENT,
            error_message="File content is empty or contains only whitespace",
        )

        # Act
        result = await process_single_file_upload(
            batch_id=batch_id,
            file_content=file_content,
            file_name=file_name,
            main_correlation_id=correlation_id,
            text_extractor=mock_text_extractor,
            content_validator=mock_content_validator,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
        )

        # Assert validation failure
        assert result["status"] == FileProcessingStatus.CONTENT_VALIDATION_FAILED.value
        assert result["error_code"] == FileValidationErrorCode.EMPTY_CONTENT
        assert "empty or contains only whitespace" in result["error_message"]
        assert result["raw_file_storage_id"] == "raw_storage_empty_123"

        # Verify raw storage was called (NEW BEHAVIOR)
        mock_content_client.store_content.assert_called_once_with(
            file_content,
            ContentType.RAW_UPLOAD_BLOB,
        )

        # Verify validation failure event published with empty content details
        mock_event_publisher.publish_essay_validation_failed.assert_called_once()
        failure_event_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_event_call[0][0]
        assert event_data.validation_error_code == FileValidationErrorCode.EMPTY_CONTENT
        assert event_data.file_size_bytes == 0
        assert event_data.raw_file_storage_id == "raw_storage_empty_123"

    @pytest.mark.asyncio
    async def test_content_too_long_validation_failure(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling of content too long validation failure."""
        # Arrange
        batch_id = TEST_BATCH_IDS["too_long"]
        file_content = b"A" * 10000  # Very long content
        file_name = TEST_FILE_NAMES["long"]
        correlation_id = uuid.uuid4()

        # Configure mocks for new pre-emptive raw storage behavior
        mock_content_client.store_content.return_value = "raw_storage_long_456"
        mock_text_extractor.extract_text.return_value = "A" * 10000

        mock_content_validator.validate_content.return_value = ValidationResult(
            is_valid=False,
            error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
            error_message="Content length (10000 characters) exceeds maximum threshold (5000)",
        )

        # Act
        result = await process_single_file_upload(
            batch_id=batch_id,
            file_content=file_content,
            file_name=file_name,
            main_correlation_id=correlation_id,
            text_extractor=mock_text_extractor,
            content_validator=mock_content_validator,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
        )

        # Assert validation failure
        assert result["status"] == FileProcessingStatus.CONTENT_VALIDATION_FAILED.value
        assert result["error_code"] == FileValidationErrorCode.CONTENT_TOO_LONG
        assert "10000 characters" in result["error_message"]
        assert result["raw_file_storage_id"] == "raw_storage_long_456"

        # Verify raw storage was called (NEW BEHAVIOR)
        mock_content_client.store_content.assert_called_once_with(
            file_content,
            ContentType.RAW_UPLOAD_BLOB,
        )

        # Verify appropriate event published for long content
        mock_event_publisher.publish_essay_validation_failed.assert_called_once()
        failure_event_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_event_call[0][0]
        assert event_data.validation_error_code == FileValidationErrorCode.CONTENT_TOO_LONG
        assert event_data.file_size_bytes == len(file_content)
        assert event_data.raw_file_storage_id == "raw_storage_long_456"

    @pytest.mark.asyncio
    async def test_validation_failure_event_correlation_ids(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test correlation ID propagation for validation failure events."""
        # Arrange
        batch_id = TEST_BATCH_IDS["fail_correlation"]
        file_content = b"Short"
        file_name = TEST_FILE_NAMES["fail_correlation"]
        correlation_id = uuid.uuid4()

        # Configure mocks for new pre-emptive raw storage behavior
        mock_content_client.store_content.return_value = "raw_storage_corr_789"
        mock_text_extractor.extract_text.return_value = "Short"

        mock_content_validator.validate_content.return_value = ValidationResult(
            is_valid=False,
            error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            error_message="Content too short",
        )

        # Act
        await process_single_file_upload(
            batch_id=batch_id,
            file_content=file_content,
            file_name=file_name,
            main_correlation_id=correlation_id,
            text_extractor=mock_text_extractor,
            content_validator=mock_content_validator,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
        )

        # Verify raw storage was called (NEW BEHAVIOR)
        mock_content_client.store_content.assert_called_once_with(
            file_content,
            ContentType.RAW_UPLOAD_BLOB,
        )

        # Assert correlation ID propagation for failure event
        failure_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_call[0][0]
        passed_correlation_id = failure_call[0][1]
        assert event_data.correlation_id == correlation_id
        assert passed_correlation_id == correlation_id
        assert event_data.validation_error_code == FileValidationErrorCode.CONTENT_TOO_SHORT
        assert event_data.raw_file_storage_id == "raw_storage_corr_789"

    @pytest.mark.asyncio
    async def test_empty_text_from_successful_extraction_goes_to_validation(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """
        Test that empty text from successful extraction properly goes through content validation.

        This demonstrates the elegant separation of concerns:
        - Text extraction succeeds (returns empty string)
        - Content validation handles the empty content with proper error code
        """
        # Arrange
        batch_id = TEST_BATCH_IDS["empty_success"]
        file_content = ZERO_BYTE_CONTENT
        file_name = TEST_FILE_NAMES["empty_success"]
        correlation_id = uuid.uuid4()

        # Configure mocks for new pre-emptive raw storage behavior
        mock_content_client.store_content.return_value = "raw_storage_empty_extract_999"

        # Configure extraction to successfully return empty string
        mock_text_extractor.extract_text.return_value = ""

        # Configure validation to properly handle empty content
        mock_content_validator.validate_content.return_value = ValidationResult(
            is_valid=False,
            error_code=FileValidationErrorCode.EMPTY_CONTENT,
            error_message=f"File '{file_name}' contains no readable text content.",
        )

        # Act
        result = await process_single_file_upload(
            batch_id=batch_id,
            file_content=file_content,
            file_name=file_name,
            main_correlation_id=correlation_id,
            text_extractor=mock_text_extractor,
            content_validator=mock_content_validator,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
        )

        # Assert - Text extraction succeeded, content validation failed
        assert result["status"] == FileProcessingStatus.CONTENT_VALIDATION_FAILED.value
        assert result["error_code"] == FileValidationErrorCode.EMPTY_CONTENT
        assert result["raw_file_storage_id"] == "raw_storage_empty_extract_999"

        # Verify text extraction was called and succeeded
        mock_text_extractor.extract_text.assert_called_once_with(file_content, file_name)

        # Verify validation was called with empty string
        mock_content_validator.validate_content.assert_called_once_with("", file_name)

        # Verify raw storage was called (NEW BEHAVIOR)
        mock_content_client.store_content.assert_called_once_with(
            file_content,
            ContentType.RAW_UPLOAD_BLOB,
        )

        # Verify content validation failure event was published with correct error code
        mock_event_publisher.publish_essay_validation_failed.assert_called_once()
        failure_event_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_event_call[0][0]
        assert event_data.validation_error_code == FileValidationErrorCode.EMPTY_CONTENT
        assert "contains no readable text content" in event_data.validation_error_message
        assert event_data.raw_file_storage_id == "raw_storage_empty_extract_999"

        # Verify success event was NOT published
        mock_event_publisher.publish_essay_content_provisioned.assert_not_called()
