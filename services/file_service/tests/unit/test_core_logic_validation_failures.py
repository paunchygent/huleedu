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
from common_core.status_enums import ProcessingStatus
from huleedu_service_libs.error_handling.file_validation_factories import (
    raise_content_too_long,
    raise_content_too_short,
    raise_empty_content_error,
)

from services.file_service.core_logic import process_single_file_upload
from services.file_service.tests.unit.core_logic_validation_utils import (
    EMPTY_FILE_CONTENT,
    TEST_BATCH_IDS,
    TEST_FILE_NAMES,
    ZERO_BYTE_CONTENT,
)


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
        def mock_validation_failure(text: str, file_name: str, correlation_id: uuid.UUID) -> None:
            raise_content_too_short(
                service="file_service",
                operation="validate_content",
                file_name=file_name,
                min_length=50,
                actual_length=len(text),
                correlation_id=correlation_id,
            )

        mock_content_validator.validate_content.side_effect = mock_validation_failure

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

        # Assert validation failure response
        assert result["file_name"] == file_name
        assert result["status"] == ProcessingStatus.FAILED.value
        assert result["error_code"] == FileValidationErrorCode.CONTENT_TOO_SHORT
        # Updated to match HuleEduError factory message format
        assert "actual: 10" in result["error_message"] and "minimum: 50" in result["error_message"]
        assert result["raw_file_storage_id"] == "raw_storage_12345"
        assert "text_storage_id" not in result  # Only raw storage for validation failures

        # Verify text extraction was called
        # Note: correlation_id is auto-generated, so we verify the call was made
        mock_text_extractor.extract_text.assert_called_once()
        # Verify the first two arguments are file_content and file_name
        call_args = mock_text_extractor.extract_text.call_args[0]
        assert call_args[0] == file_content
        assert call_args[1] == file_name
        assert len(call_args) == 3  # file_content + file_name + correlation_id

        # Verify validation was called
        # Note: correlation_id is auto-generated, so we verify the call was made
        mock_content_validator.validate_content.assert_called_once()
        # Verify the first two arguments are text and file_name
        call_args = mock_content_validator.validate_content.call_args[0]
        assert call_args[0] == "Short text"
        assert call_args[1] == file_name
        assert len(call_args) == 3  # text + file_name + correlation_id

        # Verify content storage was called ONCE for raw storage (NEW BEHAVIOR)
        # Note: store_content now includes correlation_id as third parameter
        mock_content_client.store_content.assert_called_once()
        # Verify the call arguments
        call_args = mock_content_client.store_content.call_args[0]
        assert call_args[0] == file_content  # content_bytes
        assert call_args[1] == ContentType.RAW_UPLOAD_BLOB  # content_type
        assert len(call_args) == 3  # content_bytes + content_type + correlation_id

        # Verify validation failure event was published
        mock_event_publisher.publish_essay_validation_failed.assert_called_once()
        failure_event_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_event_call[0][0]
        assert isinstance(event_data, EssayValidationFailedV1)
        assert event_data.entity_id == batch_id
        assert event_data.file_upload_id == file_upload_id
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

        def mock_empty_content_failure(
            text: str, file_name: str, correlation_id: uuid.UUID
        ) -> None:
            raise_empty_content_error(
                service="file_service",
                operation="validate_content",
                file_name=file_name,
                correlation_id=correlation_id,
            )

        mock_content_validator.validate_content.side_effect = mock_empty_content_failure

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

        # Assert validation failure
        assert result["status"] == ProcessingStatus.FAILED.value
        assert result["error_code"] == FileValidationErrorCode.EMPTY_CONTENT
        # Updated to match HuleEduError factory message format
        assert "has empty content" in result["error_message"]
        assert result["raw_file_storage_id"] == "raw_storage_empty_123"

        # Verify raw storage was called (NEW BEHAVIOR)
        # Note: store_content now includes correlation_id as third parameter
        mock_content_client.store_content.assert_called_once()
        # Verify the call arguments
        call_args = mock_content_client.store_content.call_args[0]
        assert call_args[0] == file_content  # content_bytes
        assert call_args[1] == ContentType.RAW_UPLOAD_BLOB  # content_type
        assert len(call_args) == 3  # content_bytes + content_type + correlation_id

        # Verify validation failure event published with empty content details
        mock_event_publisher.publish_essay_validation_failed.assert_called_once()
        failure_event_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_event_call[0][0]
        assert event_data.file_upload_id == file_upload_id
        assert event_data.entity_id == batch_id
        assert event_data.original_file_name == file_name
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

        def mock_content_too_long_failure(
            text: str, file_name: str, correlation_id: uuid.UUID
        ) -> None:
            raise_content_too_long(
                service="file_service",
                operation="validate_content",
                file_name=file_name,
                max_length=5000,
                actual_length=len(text),
                correlation_id=correlation_id,
            )

        mock_content_validator.validate_content.side_effect = mock_content_too_long_failure

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

        # Assert validation failure
        assert result["status"] == ProcessingStatus.FAILED.value
        assert result["error_code"] == FileValidationErrorCode.CONTENT_TOO_LONG
        # Updated to match HuleEduError factory message format
        assert "maximum: 5000" in result["error_message"]
        assert "actual: 10000" in result["error_message"]
        assert result["raw_file_storage_id"] == "raw_storage_long_456"

        # Verify raw storage was called (NEW BEHAVIOR)
        # Note: store_content now includes correlation_id as third parameter
        mock_content_client.store_content.assert_called_once()
        # Verify the call arguments
        call_args = mock_content_client.store_content.call_args[0]
        assert call_args[0] == file_content  # content_bytes
        assert call_args[1] == ContentType.RAW_UPLOAD_BLOB  # content_type
        assert len(call_args) == 3  # content_bytes + content_type + correlation_id

        # Verify appropriate event published for long content
        mock_event_publisher.publish_essay_validation_failed.assert_called_once()
        failure_event_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_event_call[0][0]
        assert event_data.file_upload_id == file_upload_id
        assert event_data.entity_id == batch_id
        assert event_data.original_file_name == file_name
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

        def mock_short_content_failure(
            text: str, file_name: str, correlation_id: uuid.UUID
        ) -> None:
            raise_content_too_short(
                service="file_service",
                operation="validate_content",
                file_name=file_name,
                min_length=50,
                actual_length=len(text),
                correlation_id=correlation_id,
            )

        mock_content_validator.validate_content.side_effect = mock_short_content_failure

        # Act
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

        # Verify raw storage was called (NEW BEHAVIOR)
        # Note: store_content now includes correlation_id as third parameter
        mock_content_client.store_content.assert_called_once()
        # Verify the call arguments
        call_args = mock_content_client.store_content.call_args[0]
        assert call_args[0] == file_content  # content_bytes
        assert call_args[1] == ContentType.RAW_UPLOAD_BLOB  # content_type
        assert len(call_args) == 3  # content_bytes + content_type + correlation_id

        # Assert correlation ID propagation for failure event
        failure_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_call[0][0]
        passed_correlation_id = failure_call[0][1]
        assert event_data.correlation_id == correlation_id
        assert passed_correlation_id == correlation_id
        assert event_data.file_upload_id == file_upload_id
        assert event_data.entity_id == batch_id
        assert event_data.original_file_name == file_name
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
        def mock_empty_validation_failure(
            text: str, file_name: str, correlation_id: uuid.UUID
        ) -> None:
            raise_empty_content_error(
                service="file_service",
                operation="validate_content",
                file_name=file_name,
                correlation_id=correlation_id,
            )

        mock_content_validator.validate_content.side_effect = mock_empty_validation_failure

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

        # Assert - Text extraction succeeded, content validation failed
        assert result["status"] == ProcessingStatus.FAILED.value
        assert result["error_code"] == FileValidationErrorCode.EMPTY_CONTENT
        assert result["raw_file_storage_id"] == "raw_storage_empty_extract_999"

        # Verify text extraction was called and succeeded
        # Note: correlation_id is auto-generated, so we verify the call was made
        mock_text_extractor.extract_text.assert_called_once()
        # Verify the first two arguments are file_content and file_name
        call_args = mock_text_extractor.extract_text.call_args[0]
        assert call_args[0] == file_content
        assert call_args[1] == file_name
        assert len(call_args) == 3  # file_content + file_name + correlation_id

        # Verify validation was called with empty string
        # Note: correlation_id is auto-generated, so we verify the call was made
        mock_content_validator.validate_content.assert_called_once()
        # Verify the first two arguments are text and file_name
        call_args = mock_content_validator.validate_content.call_args[0]
        assert call_args[0] == ""
        assert call_args[1] == file_name
        assert len(call_args) == 3  # text + file_name + correlation_id

        # Verify raw storage was called (NEW BEHAVIOR)
        # Note: store_content now includes correlation_id as third parameter
        mock_content_client.store_content.assert_called_once()
        # Verify the call arguments
        call_args = mock_content_client.store_content.call_args[0]
        assert call_args[0] == file_content  # content_bytes
        assert call_args[1] == ContentType.RAW_UPLOAD_BLOB  # content_type
        assert len(call_args) == 3  # content_bytes + content_type + correlation_id

        # Verify content validation failure event was published with correct error code
        mock_event_publisher.publish_essay_validation_failed.assert_called_once()
        failure_event_call = mock_event_publisher.publish_essay_validation_failed.call_args
        event_data = failure_event_call[0][0]
        assert event_data.file_upload_id == file_upload_id
        assert event_data.entity_id == batch_id
        assert event_data.original_file_name == file_name
        assert event_data.validation_error_code == FileValidationErrorCode.EMPTY_CONTENT
        assert "has empty content" in event_data.validation_error_detail.message
        assert event_data.raw_file_storage_id == "raw_storage_empty_extract_999"

        # Verify success event was NOT published
        mock_event_publisher.publish_essay_content_provisioned.assert_not_called()
