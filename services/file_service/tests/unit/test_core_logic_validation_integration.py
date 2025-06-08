"""
Integration tests for core logic with validation framework.

Tests the complete file processing workflow including validation
integration, event publishing, and proper error handling.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from services.file_service.core_logic import process_single_file_upload
from services.file_service.validation_models import ValidationResult


class TestCoreLogicValidationIntegration:
    """Test suite for core logic validation integration."""

    @pytest.fixture
    def mock_text_extractor(self) -> AsyncMock:
        """Create mock text extractor."""
        extractor = AsyncMock()
        extractor.extract_text.return_value = "This is a valid essay content with sufficient length for validation."
        return extractor

    @pytest.fixture
    def mock_content_validator(self) -> AsyncMock:
        """Create mock content validator."""
        validator = AsyncMock()
        # Default to valid content
        validator.validate_content.return_value = ValidationResult(
            is_valid=True,
            error_code=None,
            error_message=None
        )
        return validator

    @pytest.fixture
    def mock_content_client(self) -> AsyncMock:
        """Create mock content service client."""
        client = AsyncMock()
        client.store_content.return_value = "storage_id_12345"
        return client

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher."""
        publisher = AsyncMock()
        publisher.publish_essay_content_provisioned.return_value = None
        publisher.publish_essay_validation_failed.return_value = None
        return publisher

    @pytest.mark.asyncio
    async def test_successful_file_processing_with_validation(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock
    ) -> None:
        """Test complete successful file processing workflow with validation."""
        # Arrange
        batch_id = "test_batch_123"
        file_content = b"Valid essay content for testing"
        file_name = "essay1.txt"
        correlation_id = uuid.uuid4()

        # Act
        result = await process_single_file_upload(
            batch_id=batch_id,
            file_content=file_content,
            file_name=file_name,
            main_correlation_id=correlation_id,
            text_extractor=mock_text_extractor,
            content_validator=mock_content_validator,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher
        )

        # Assert workflow completion
        assert result["file_name"] == file_name
        assert result["status"] == "processing_success"
        assert result["text_storage_id"] == "storage_id_12345"

        # Verify text extraction was called
        mock_text_extractor.extract_text.assert_called_once_with(file_content, file_name)

        # Verify validation was called
        mock_content_validator.validate_content.assert_called_once()
        validation_call_args = mock_content_validator.validate_content.call_args
        assert len(validation_call_args[0]) == 2  # text and file_name
        assert validation_call_args[0][1] == file_name

        # Verify content storage was called
        mock_content_client.store_content.assert_called_once()

        # Verify success event was published
        mock_event_publisher.publish_essay_content_provisioned.assert_called_once()
        success_event_call = mock_event_publisher.publish_essay_content_provisioned.call_args
        event_data = success_event_call[0][0]
        assert isinstance(event_data, EssayContentProvisionedV1)
        assert event_data.batch_id == batch_id
        assert event_data.original_file_name == file_name

        # Verify validation failure event was NOT published
        mock_event_publisher.publish_essay_validation_failed.assert_not_called()

    @pytest.mark.asyncio
    async def test_validation_failure_workflow(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock
    ) -> None:
        """Test validation failure workflow with proper event publishing."""
        # Arrange
        batch_id = "test_batch_456"
        file_content = b"Empty"
        file_name = "empty_essay.txt"
        correlation_id = uuid.uuid4()

        # Configure validation to fail
        mock_content_validator.validate_content.return_value = ValidationResult(
            is_valid=False,
            error_code="CONTENT_TOO_SHORT",
            error_message="Content length (5 characters) below minimum threshold (50)"
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
            event_publisher=mock_event_publisher
        )

        # Assert validation failure response
        assert result["file_name"] == file_name
        assert result["status"] == "content_validation_failed"
        assert result["error_code"] == "CONTENT_TOO_SHORT"
        assert "5 characters" in result["error_message"]
        assert "text_storage_id" not in result

        # Verify text extraction was called
        mock_text_extractor.extract_text.assert_called_once_with(file_content, file_name)

        # Verify validation was called
        mock_content_validator.validate_content.assert_called_once()

        # Verify content storage was NOT called (validation failed)
        mock_content_client.store_content.assert_not_called()

        # Verify validation failure event was published
        mock_event_publisher.publish_essay_validation_failed.assert_called_once()
        failure_event_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_event_call[0][0]
        assert isinstance(event_data, EssayValidationFailedV1)
        assert event_data.batch_id == batch_id
        assert event_data.original_file_name == file_name
        assert event_data.validation_error_code == "CONTENT_TOO_SHORT"
        assert event_data.file_size_bytes == len(file_content)

        # Verify success event was NOT published
        mock_event_publisher.publish_essay_content_provisioned.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_content_validation_failure(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock
    ) -> None:
        """Test handling of empty content validation failure."""
        # Arrange
        batch_id = "test_batch_empty"
        file_content = b""
        file_name = "empty_file.txt"
        correlation_id = uuid.uuid4()

        mock_content_validator.validate_content.return_value = ValidationResult(
            is_valid=False,
            error_code="EMPTY_CONTENT",
            error_message="File content is empty or contains only whitespace"
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
            event_publisher=mock_event_publisher
        )

        # Assert
        assert result["status"] == "content_validation_failed"
        assert result["error_code"] == "EMPTY_CONTENT"

        # Verify validation failure event includes correct file size
        mock_event_publisher.publish_essay_validation_failed.assert_called_once()
        failure_event_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_event_call[0][0]
        assert event_data.file_size_bytes == 0  # Empty file

    @pytest.mark.asyncio
    async def test_content_too_long_validation_failure(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock
    ) -> None:
        """Test handling of content too long validation failure."""
        # Arrange
        batch_id = "test_batch_long"
        file_content = b"Very long content" * 1000  # Large content
        file_name = "huge_essay.txt"
        correlation_id = uuid.uuid4()

        mock_content_validator.validate_content.return_value = ValidationResult(
            is_valid=False,
            error_code="CONTENT_TOO_LONG",
            error_message="Content exceeds maximum length limit (50000 characters)"
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
            event_publisher=mock_event_publisher
        )

        # Assert
        assert result["status"] == "content_validation_failed"
        assert result["error_code"] == "CONTENT_TOO_LONG"

        # Verify validation failure event includes correct file size
        mock_event_publisher.publish_essay_validation_failed.assert_called_once()
        failure_event_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_event_call[0][0]
        assert event_data.file_size_bytes == len(file_content)

    @pytest.mark.asyncio
    async def test_text_extraction_failure_before_validation(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock
    ) -> None:
        """Test that validation is called when text extraction returns empty but true extraction failures are separate."""
        # Arrange
        batch_id = "test_batch_extract_fail"
        file_content = b"corrupted file content"
        file_name = "corrupted.txt"
        correlation_id = uuid.uuid4()

        # Configure extraction to RAISE an exception (true technical failure)
        mock_text_extractor.extract_text.side_effect = Exception("File format not supported")

        # Act
        result = await process_single_file_upload(
            batch_id=batch_id,
            file_content=file_content,
            file_name=file_name,
            main_correlation_id=correlation_id,
            text_extractor=mock_text_extractor,
            content_validator=mock_content_validator,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher
        )

        # Assert
        assert result["status"] == "extraction_failed"

        # Verify text extraction was attempted
        mock_text_extractor.extract_text.assert_called_once_with(file_content, file_name)

        # Verify validation was NOT called (extraction failed)
        mock_content_validator.validate_content.assert_not_called()

        # Verify technical extraction failure event was published
        mock_event_publisher.publish_essay_validation_failed.assert_called_once()
        failure_event_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_event_call[0][0]
        assert event_data.validation_error_code == "TEXT_EXTRACTION_FAILED"
        assert "Technical text extraction failure" in event_data.validation_error_message

        # Verify success event was NOT published
        mock_event_publisher.publish_essay_content_provisioned.assert_not_called()

    @pytest.mark.asyncio
    async def test_content_service_error_after_validation_success(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock
    ) -> None:
        """Test handling of content service errors after successful validation."""
        # Arrange
        batch_id = "test_batch_storage_fail"
        file_content = b"Valid content that passes validation"
        file_name = "valid_essay.txt"
        correlation_id = uuid.uuid4()

        # Configure content client to fail
        mock_content_client.store_content.side_effect = RuntimeError("Content Service unavailable")

        # Act
        result = await process_single_file_upload(
            batch_id=batch_id,
            file_content=file_content,
            file_name=file_name,
            main_correlation_id=correlation_id,
            text_extractor=mock_text_extractor,
            content_validator=mock_content_validator,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher
        )

        # Assert
        assert result["status"] == "processing_error"
        assert "Content Service unavailable" in result["detail"]

        # Verify validation was called and passed
        mock_content_validator.validate_content.assert_called_once()

        # Verify no events were published (storage failed)
        mock_event_publisher.publish_essay_content_provisioned.assert_not_called()
        mock_event_publisher.publish_essay_validation_failed.assert_not_called()

    @pytest.mark.asyncio
    async def test_event_correlation_ids_are_propagated(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock
    ) -> None:
        """Test that correlation IDs are properly propagated to events."""
        # Arrange
        batch_id = "test_batch_correlation"
        file_content = b"Content for correlation ID testing"
        file_name = "correlation_test.txt"
        correlation_id = uuid.uuid4()

        # Act - successful validation
        await process_single_file_upload(
            batch_id=batch_id,
            file_content=file_content,
            file_name=file_name,
            main_correlation_id=correlation_id,
            text_extractor=mock_text_extractor,
            content_validator=mock_content_validator,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher
        )

        # Assert correlation ID propagation for success event
        success_call = mock_event_publisher.publish_essay_content_provisioned.call_args
        event_data = success_call[0][0]
        passed_correlation_id = success_call[0][1]
        assert event_data.correlation_id == correlation_id
        assert passed_correlation_id == correlation_id

    @pytest.mark.asyncio
    async def test_validation_failure_event_correlation_ids(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock
    ) -> None:
        """Test correlation ID propagation for validation failure events."""
        # Arrange
        batch_id = "test_batch_fail_correlation"
        file_content = b"Short"
        file_name = "short_essay.txt"
        correlation_id = uuid.uuid4()

        mock_content_validator.validate_content.return_value = ValidationResult(
            is_valid=False,
            error_code="CONTENT_TOO_SHORT",
            error_message="Content too short"
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
            event_publisher=mock_event_publisher
        )

        # Assert correlation ID propagation for failure event
        failure_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_call[0][0]
        passed_correlation_id = failure_call[0][1]
        assert event_data.correlation_id == correlation_id
        assert passed_correlation_id == correlation_id

    @pytest.mark.asyncio
    async def test_empty_text_from_successful_extraction_goes_to_validation(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock
    ) -> None:
        """
        Test that empty text from successful extraction properly goes through content validation.
        
        This demonstrates the elegant separation of concerns:
        - Text extraction succeeds (returns empty string)
        - Content validation handles the empty content with proper error code
        """
        # Arrange
        batch_id = "test_batch_empty_success"
        file_content = b""  # Empty file
        file_name = "empty.txt"
        correlation_id = uuid.uuid4()

        # Configure extraction to successfully return empty string
        mock_text_extractor.extract_text.return_value = ""

        # Configure validation to properly handle empty content
        mock_content_validator.validate_content.return_value = ValidationResult(
            is_valid=False,
            error_code="EMPTY_CONTENT",
            error_message="File 'empty.txt' contains no readable text content."
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
            event_publisher=mock_event_publisher
        )

        # Assert - Text extraction succeeded, content validation failed
        assert result["status"] == "content_validation_failed"
        assert result["error_code"] == "EMPTY_CONTENT"

        # Verify text extraction was called and succeeded
        mock_text_extractor.extract_text.assert_called_once_with(file_content, file_name)

        # Verify validation was called with empty string
        mock_content_validator.validate_content.assert_called_once_with("", file_name)

        # Verify content validation failure event was published with correct error code
        mock_event_publisher.publish_essay_validation_failed.assert_called_once()
        failure_event_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_event_call[0][0]
        assert event_data.validation_error_code == "EMPTY_CONTENT"
        assert "contains no readable text content" in event_data.validation_error_message

        # Verify content storage was NOT called (validation failed)
        mock_content_client.store_content.assert_not_called()

        # Verify success event was NOT published
        mock_event_publisher.publish_essay_content_provisioned.assert_not_called()
