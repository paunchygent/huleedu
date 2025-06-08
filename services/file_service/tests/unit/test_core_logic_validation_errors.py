"""
Tests for error handling workflows in core logic validation integration.

Tests error scenarios including text extraction failures, content service errors,
and proper error event publishing.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from services.file_service.core_logic import process_single_file_upload
from services.file_service.tests.unit.core_logic_validation_utils import (
    TEST_BATCH_IDS,
    TEST_FILE_NAMES,
)


class TestCoreLogicValidationErrors:
    """Test suite for error handling scenarios in core logic integration."""

    @pytest.mark.asyncio
    async def test_text_extraction_failure_before_validation(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling of text extraction failures before validation."""
        # Arrange
        batch_id = TEST_BATCH_IDS["extraction_failure"]
        file_content = b"Binary content that cannot be extracted"
        file_name = TEST_FILE_NAMES["extraction_fail"]
        correlation_id = uuid.uuid4()

        # Configure text extractor to fail
        mock_text_extractor.extract_text.side_effect = RuntimeError(
            "Unable to extract text from PDF"
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
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling of content service errors after successful validation."""
        # Arrange
        batch_id = TEST_BATCH_IDS["storage_failure"]
        file_content = b"Valid content that passes validation"
        file_name = TEST_FILE_NAMES["storage_fail"]
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
            event_publisher=mock_event_publisher,
        )

        # Assert
        assert result["status"] == "processing_error"
        assert "Content Service unavailable" in result["detail"]

        # Verify validation was called and passed
        mock_content_validator.validate_content.assert_called_once()

        # Verify no events were published (storage failed)
        mock_event_publisher.publish_essay_content_provisioned.assert_not_called()
        mock_event_publisher.publish_essay_validation_failed.assert_not_called()
