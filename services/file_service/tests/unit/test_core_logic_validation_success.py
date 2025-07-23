"""
Tests for successful file processing workflows in core logic validation integration.

Tests the complete successful file processing workflow including validation
integration, event publishing, and proper correlation ID handling.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from common_core.domain_enums import ContentType
from common_core.events.file_events import EssayContentProvisionedV1
from common_core.status_enums import ProcessingStatus

from services.file_service.core_logic import process_single_file_upload
from services.file_service.tests.unit.core_logic_validation_utils import (
    TEST_BATCH_IDS,
    TEST_FILE_NAMES,
    VALID_FILE_CONTENT,
)


class TestCoreLogicValidationSuccess:
    """Test suite for successful core logic validation integration."""

    @pytest.mark.asyncio
    async def test_successful_file_processing_with_validation(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test complete successful file processing workflow with validation."""
        # Arrange
        batch_id = TEST_BATCH_IDS["success"]
        file_content = VALID_FILE_CONTENT
        file_name = TEST_FILE_NAMES["valid"]
        correlation_id = uuid.uuid4()

        # Configure mocks for new pre-emptive raw storage behavior
        # store_content is called TWICE: once for raw blob, once for extracted text
        mock_content_client.store_content.side_effect = [
            "raw_storage_id_12345",  # First call: raw blob storage
            "text_storage_id_67890",  # Second call: extracted text storage
        ]

        # Mock text extraction to return valid content
        extracted_text = "This is a valid essay content with sufficient length for validation."
        mock_text_extractor.extract_text.return_value = extracted_text

        # Act
        file_upload_id = str(uuid.uuid4())
        result = await process_single_file_upload(
            batch_id=batch_id,
            file_upload_id=file_upload_id,
            file_content=file_content,
            file_name=file_name,
            main_correlation_id=correlation_id,
            text_extractor=mock_text_extractor,
            content_validator=mock_content_validator,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
        )

        # Assert workflow completion
        assert result["file_name"] == file_name
        assert result["status"] == ProcessingStatus.COMPLETED.value
        assert result["raw_file_storage_id"] == "raw_storage_id_12345"
        assert result["text_storage_id"] == "text_storage_id_67890"

        # Verify text extraction was called
        # Note: correlation_id is auto-generated, so we verify the call was made
        mock_text_extractor.extract_text.assert_called_once()
        # Verify the first two arguments are file_content and file_name
        call_args = mock_text_extractor.extract_text.call_args[0]
        assert call_args[0] == file_content
        assert call_args[1] == file_name
        assert len(call_args) == 3  # file_content + file_name + correlation_id

        # Verify validation was called
        mock_content_validator.validate_content.assert_called_once()
        validation_call_args = mock_content_validator.validate_content.call_args
        assert len(validation_call_args[0]) == 3  # text, file_name, and correlation_id
        assert validation_call_args[0][0] == extracted_text  # extracted text
        assert validation_call_args[0][1] == file_name
        assert validation_call_args[0][2] == correlation_id

        # Verify content storage was called TWICE (NEW BEHAVIOR)
        assert mock_content_client.store_content.call_count == 2

        # Verify first call (raw blob storage) arguments
        first_call_args = mock_content_client.store_content.call_args_list[0][0]
        assert first_call_args[0] == file_content  # content_bytes
        assert first_call_args[1] == ContentType.RAW_UPLOAD_BLOB  # content_type
        assert len(first_call_args) == 3  # content_bytes + content_type + correlation_id

        # Verify second call (extracted text storage) arguments
        second_call_args = mock_content_client.store_content.call_args_list[1][0]
        assert second_call_args[0] == extracted_text.encode("utf-8")  # content_bytes
        assert second_call_args[1] == ContentType.EXTRACTED_PLAINTEXT  # content_type
        assert len(second_call_args) == 3  # content_bytes + content_type + correlation_id

        # Verify success event was published
        mock_event_publisher.publish_essay_content_provisioned.assert_called_once()
        success_event_call = mock_event_publisher.publish_essay_content_provisioned.call_args
        event_data = success_event_call[0][0]
        assert isinstance(event_data, EssayContentProvisionedV1)
        assert event_data.batch_id == batch_id
        assert event_data.original_file_name == file_name
        assert event_data.raw_file_storage_id == "raw_storage_id_12345"  # Raw storage ID
        assert event_data.text_storage_id == "text_storage_id_67890"  # Text storage ID

        # Verify validation failure event was NOT published
        mock_event_publisher.publish_essay_validation_failed.assert_not_called()

    @pytest.mark.asyncio
    async def test_event_correlation_ids_are_propagated(
        self,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that correlation IDs are properly propagated to events."""
        # Arrange
        batch_id = TEST_BATCH_IDS["correlation"]
        file_content = b"Content for correlation ID testing"
        file_name = TEST_FILE_NAMES["correlation"]
        correlation_id = uuid.uuid4()

        # Configure mocks for new pre-emptive raw storage behavior
        mock_content_client.store_content.side_effect = [
            "raw_storage_correlation_111",
            "text_storage_correlation_222",
        ]

        extracted_text = "Content for correlation ID testing"
        mock_text_extractor.extract_text.return_value = extracted_text

        # Act - successful validation
        file_upload_id = str(uuid.uuid4())
        await process_single_file_upload(
            batch_id=batch_id,
            file_upload_id=file_upload_id,
            file_content=file_content,
            file_name=file_name,
            main_correlation_id=correlation_id,
            text_extractor=mock_text_extractor,
            content_validator=mock_content_validator,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
        )

        # Verify content storage was called TWICE (NEW BEHAVIOR)
        assert mock_content_client.store_content.call_count == 2

        # Verify first call (raw blob storage) arguments
        first_call_args = mock_content_client.store_content.call_args_list[0][0]
        assert first_call_args[0] == file_content  # content_bytes
        assert first_call_args[1] == ContentType.RAW_UPLOAD_BLOB  # content_type
        assert len(first_call_args) == 3  # content_bytes + content_type + correlation_id

        # Verify second call (extracted text storage) arguments
        second_call_args = mock_content_client.store_content.call_args_list[1][0]
        assert second_call_args[0] == extracted_text.encode("utf-8")  # content_bytes
        assert second_call_args[1] == ContentType.EXTRACTED_PLAINTEXT  # content_type
        assert len(second_call_args) == 3  # content_bytes + content_type + correlation_id

        # Assert correlation ID propagation for success event
        success_call = mock_event_publisher.publish_essay_content_provisioned.call_args
        event_data = success_call[0][0]
        passed_correlation_id = success_call[0][1]
        assert event_data.correlation_id == correlation_id
        assert passed_correlation_id == correlation_id
        assert event_data.raw_file_storage_id == "raw_storage_correlation_111"
        assert event_data.text_storage_id == "text_storage_correlation_222"
