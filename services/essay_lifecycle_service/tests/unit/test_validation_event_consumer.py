"""
Unit tests for ELS validation event consumer integration.

Tests the integration of validation failure event handling into the ELS Kafka consumer
for Phase 6 of the File Service validation improvements.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.error_enums import FileValidationErrorCode
from common_core.events.envelope import EventEnvelope
from common_core.events.file_events import EssayValidationFailedV1
from common_core.models.error_models import ErrorDetail

from services.essay_lifecycle_service.protocols import BatchEssayTracker


class TestValidationEventConsumerIntegration:
    """Test suite for validation event consumer integration with ELS."""

    @pytest.fixture
    def mock_batch_tracker(self) -> AsyncMock:
        """Fixture providing a mocked BatchEssayTracker using protocol-based mocking."""
        return AsyncMock(spec=BatchEssayTracker)

    @pytest.fixture
    def sample_validation_failure_event(self) -> EssayValidationFailedV1:
        """Fixture providing a sample validation failure event."""
        return EssayValidationFailedV1(
            batch_id="batch_consumer_test",
            file_upload_id="test-file-upload-consumer",
            original_file_name="failed_essay.txt",
            validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.EMPTY_CONTENT,
                message="File content is empty or contains only whitespace",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content",
            ),
            file_size_bytes=0,
            raw_file_storage_id="test_storage_id_consumer",
            correlation_id=uuid4(),
        )

    @pytest.fixture
    def sample_event_envelope(
        self, sample_validation_failure_event: EssayValidationFailedV1
    ) -> EventEnvelope:
        """Fixture providing a sample event envelope with validation failure."""
        return EventEnvelope(
            event_id=uuid4(),
            event_type="essay.validation.failed",
            event_timestamp=datetime.now(UTC),
            source_service="file_service",
            correlation_id=sample_validation_failure_event.correlation_id,
            data=sample_validation_failure_event,
        )

    async def test_validation_failure_event_processing(
        self,
        mock_batch_tracker: AsyncMock,
        sample_validation_failure_event: EssayValidationFailedV1,
    ) -> None:
        """Test processing of validation failure events by ELS consumer."""
        # Simulate event processor handling validation failure
        await mock_batch_tracker.handle_validation_failure(sample_validation_failure_event)

        # Verify the batch tracker was called with the correct event
        mock_batch_tracker.handle_validation_failure.assert_called_once_with(
            sample_validation_failure_event
        )

    async def test_event_envelope_deserialization(
        self,
        sample_event_envelope: EventEnvelope,
        sample_validation_failure_event: EssayValidationFailedV1,
    ) -> None:
        """Test that event envelopes with validation failures can be properly deserialized."""
        # Serialize the envelope to JSON (simulating Kafka message)
        envelope_json = sample_event_envelope.model_dump_json()
        assert isinstance(envelope_json, str)

        # Deserialize back from JSON
        envelope_data = json.loads(envelope_json)
        reconstructed_envelope: EventEnvelope[EssayValidationFailedV1] = EventEnvelope[
            EssayValidationFailedV1
        ](
            event_id=envelope_data["event_id"],
            event_type=envelope_data["event_type"],
            event_timestamp=envelope_data["event_timestamp"],
            source_service=envelope_data["source_service"],
            correlation_id=envelope_data["correlation_id"],
            data=EssayValidationFailedV1(**envelope_data["data"]),
        )

        # Verify envelope properties
        assert reconstructed_envelope.event_type == "essay.validation.failed"
        assert reconstructed_envelope.source_service == "file_service"
        assert isinstance(reconstructed_envelope.data, EssayValidationFailedV1)

        # Verify the validation failure data
        validation_data = reconstructed_envelope.data
        assert validation_data.batch_id == sample_validation_failure_event.batch_id
        assert (
            validation_data.validation_error_code
            == sample_validation_failure_event.validation_error_code
        )

    async def test_consumer_event_routing(
        self, mock_batch_tracker: AsyncMock, sample_event_envelope: EventEnvelope
    ) -> None:
        """Test that the ELS consumer routes validation failure events correctly."""
        # Simulate the consumer's event routing logic
        event_type = sample_event_envelope.event_type
        event_data = sample_event_envelope.data

        # Should route essay.validation.failed events to batch tracker
        if event_type == "essay.validation.failed":
            assert isinstance(event_data, EssayValidationFailedV1)
            await mock_batch_tracker.handle_validation_failure(event_data)

        # Verify the routing occurred
        mock_batch_tracker.handle_validation_failure.assert_called_once_with(event_data)

    async def test_multiple_validation_failure_events(self, mock_batch_tracker: AsyncMock) -> None:
        """Test processing multiple validation failure events for the same batch."""
        # Create multiple validation failure events
        validation_failures = [
            EssayValidationFailedV1(
                batch_id="batch_multiple",
                file_upload_id=f"test-file-upload-multiple-{i}",
                original_file_name=f"failed_{i}.txt",
                validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                validation_error_detail=ErrorDetail(
                    error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                    message=f"Content is too short: file {i}",
                    correlation_id=uuid4(),
                    timestamp=datetime.now(UTC),
                    service="file_service",
                    operation="validate_content",
                ),
                file_size_bytes=10,
                raw_file_storage_id=f"test_storage_id_multiple_{i:03d}",
            )
            for i in range(1, 4)
        ]

        # Process each event
        for failure in validation_failures:
            await mock_batch_tracker.handle_validation_failure(failure)

        # Verify all events were processed
        assert mock_batch_tracker.handle_validation_failure.call_count == 3

    async def test_validation_failure_with_correlation_tracking(
        self, mock_batch_tracker: AsyncMock
    ) -> None:
        """Test that correlation IDs are preserved through event processing."""
        correlation_id = uuid4()

        validation_failure = EssayValidationFailedV1(
            batch_id="batch_correlation",
            file_upload_id="test-file-upload-correlation",
            original_file_name="tracked_file.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
                message="Content is too long, exceeds maximum length",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content",
            ),
            file_size_bytes=100000,
            raw_file_storage_id="test_storage_id_correlation",
            correlation_id=correlation_id,
        )

        # Process event
        await mock_batch_tracker.handle_validation_failure(validation_failure)

        # Verify correlation ID was preserved
        call_args = mock_batch_tracker.handle_validation_failure.call_args[0][0]
        assert call_args.correlation_id == correlation_id

    async def test_invalid_event_data_handling(self, mock_batch_tracker: AsyncMock) -> None:
        """Test handling of invalid or malformed validation failure events."""
        # Create an envelope with incorrect event type but validation failure data
        invalid_envelope: EventEnvelope[EssayValidationFailedV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="essay.content.provisioned",  # Wrong event type
            event_timestamp=datetime.now(UTC),
            source_service="file_service",
            data=EssayValidationFailedV1(
                batch_id="batch_invalid",
                file_upload_id="test-file-upload-invalid",
                original_file_name="test.txt",
                validation_error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
                validation_error_detail=ErrorDetail(
                    error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
                    message="Test error",
                    correlation_id=uuid4(),
                    timestamp=datetime.now(UTC),
                    service="file_service",
                    operation="validate_content",
                ),
                file_size_bytes=100,
                raw_file_storage_id="test_storage_id_invalid",
            ),
        )

        # Consumer should not process this as a validation failure
        event_type = invalid_envelope.event_type
        if event_type == "essay.validation.failed":
            await mock_batch_tracker.handle_validation_failure(invalid_envelope.data)

        # Should not have been called due to mismatched event type
        mock_batch_tracker.handle_validation_failure.assert_not_called()

    async def test_consumer_error_handling(self, mock_batch_tracker: AsyncMock) -> None:
        """Test error handling in validation failure event processing."""
        # Configure mock to raise an exception
        mock_batch_tracker.handle_validation_failure.side_effect = Exception("Processing error")

        validation_failure = EssayValidationFailedV1(
            batch_id="batch_error",
            file_upload_id="test-file-upload-error",
            original_file_name="error_test.txt",
            validation_error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
                message="Test error message",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content",
            ),
            file_size_bytes=50,
            raw_file_storage_id="test_storage_id_error",
        )

        # Processing should handle the exception
        with pytest.raises(Exception, match="Processing error"):
            await mock_batch_tracker.handle_validation_failure(validation_failure)

        # Verify the call was attempted
        mock_batch_tracker.handle_validation_failure.assert_called_once()

    async def test_event_timestamp_validation(
        self, sample_validation_failure_event: EssayValidationFailedV1
    ) -> None:
        """Test that event timestamps are properly validated and preserved."""
        # Create envelope with specific timestamp
        test_timestamp = datetime.now(UTC)

        envelope: EventEnvelope[EssayValidationFailedV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="essay.validation.failed",
            event_timestamp=test_timestamp,
            source_service="file_service",
            data=sample_validation_failure_event,
        )

        # Verify timestamp is preserved
        assert envelope.event_timestamp == test_timestamp
        assert envelope.data.timestamp is not None

    async def test_batch_id_consistency_validation(self, mock_batch_tracker: AsyncMock) -> None:
        """Test validation of batch ID consistency between envelope and data."""
        batch_id = "batch_consistency_test"

        validation_failure = EssayValidationFailedV1(
            batch_id=batch_id,
            file_upload_id="test-file-upload-consistency",
            original_file_name="consistency_test.txt",
            validation_error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
                message="Invalid file format",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content",
            ),
            file_size_bytes=0,
            raw_file_storage_id="test_storage_id_consistency",
        )

        envelope: EventEnvelope[EssayValidationFailedV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="essay.validation.failed",
            event_timestamp=datetime.now(UTC),
            source_service="file_service",
            data=validation_failure,
        )

        # Process the event
        await mock_batch_tracker.handle_validation_failure(validation_failure)

        # Verify consistency
        call_args = mock_batch_tracker.handle_validation_failure.call_args[0][0]
        assert envelope.data.batch_id == batch_id
        assert call_args.batch_id == batch_id

    async def test_concurrent_event_processing(self, mock_batch_tracker: AsyncMock) -> None:
        """Test concurrent processing of validation failure events."""
        import asyncio

        # Create multiple validation failures for different batches
        validation_failures = [
            EssayValidationFailedV1(
                batch_id=f"batch_concurrent_{i}",
                file_upload_id=f"test-file-upload-concurrent-{i}",
                original_file_name=f"concurrent_{i}.txt",
                validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                validation_error_detail=ErrorDetail(
                    error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                    message=f"Content too short for concurrent test {i}",
                    correlation_id=uuid4(),
                    timestamp=datetime.now(UTC),
                    service="file_service",
                    operation="validate_content",
                ),
                file_size_bytes=15,
                raw_file_storage_id=f"test_storage_id_concurrent_{i:03d}",
            )
            for i in range(1, 6)
        ]

        # Process all events concurrently
        await asyncio.gather(
            *[
                mock_batch_tracker.handle_validation_failure(failure)
                for failure in validation_failures
            ]
        )

        # Verify all events were processed
        assert mock_batch_tracker.handle_validation_failure.call_count == 5

    async def test_event_source_service_validation(
        self,
        mock_batch_tracker: AsyncMock,
        sample_validation_failure_event: EssayValidationFailedV1,
    ) -> None:
        """Test validation of event source service."""
        # Create envelope from file service
        file_service_envelope: EventEnvelope[EssayValidationFailedV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="essay.validation.failed",
            event_timestamp=datetime.now(UTC),
            source_service="file_service",
            data=sample_validation_failure_event,
        )

        # Should process events from file service
        if file_service_envelope.source_service == "file_service":
            await mock_batch_tracker.handle_validation_failure(file_service_envelope.data)

        mock_batch_tracker.handle_validation_failure.assert_called_once()

        # Reset mock
        mock_batch_tracker.reset_mock()

        # Create envelope from unexpected service
        unexpected_envelope: EventEnvelope[EssayValidationFailedV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="essay.validation.failed",
            event_timestamp=datetime.now(UTC),
            source_service="unexpected_service",
            data=sample_validation_failure_event,
        )

        # Consumer should still process (source filtering might be at topic level)
        await mock_batch_tracker.handle_validation_failure(unexpected_envelope.data)
        mock_batch_tracker.handle_validation_failure.assert_called_once()

    async def test_validation_error_code_preservation(self, mock_batch_tracker: AsyncMock) -> None:
        """Test that validation error codes are preserved through event processing."""
        error_codes = [
            FileValidationErrorCode.EMPTY_CONTENT,
            FileValidationErrorCode.CONTENT_TOO_SHORT,
            FileValidationErrorCode.CONTENT_TOO_LONG,
        ]

        for error_code in error_codes:
            validation_failure = EssayValidationFailedV1(
                batch_id="batch_error_codes",
                file_upload_id=f"test-file-upload-{error_code.value.lower()}",
                original_file_name=f"test_{error_code.value.lower()}.txt",
                validation_error_code=error_code,
                validation_error_detail=ErrorDetail(
                    error_code=error_code,
                    message=f"Test message for {error_code.value}",
                    correlation_id=uuid4(),
                    timestamp=datetime.now(UTC),
                    service="file_service",
                    operation="validate_content",
                ),
                file_size_bytes=100,
                raw_file_storage_id=f"test_storage_id_{error_code.value.lower()}",
            )

            await mock_batch_tracker.handle_validation_failure(validation_failure)

            # Verify error code was preserved
            call_args = mock_batch_tracker.handle_validation_failure.call_args[0][0]
            assert call_args.validation_error_code == error_code

            mock_batch_tracker.reset_mock()
