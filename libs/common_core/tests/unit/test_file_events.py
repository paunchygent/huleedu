"""
Unit tests for file event models.

Tests the event models used by File Service for content provisioning
and validation failure notifications.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from common_core.error_enums import FileValidationErrorCode
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1


class TestEssayContentProvisionedV1:
    """Test suite for EssayContentProvisionedV1 event model."""

    def test_model_creation_with_required_fields(self) -> None:
        """Test creating EssayContentProvisionedV1 with only required fields."""
        model = EssayContentProvisionedV1(
            batch_id="batch_123",
            original_file_name="essay.txt",
            raw_file_storage_id="raw_abc123",
            text_storage_id="text_def456",
            file_size_bytes=1024,
        )
        assert model.batch_id == "batch_123"
        assert model.original_file_name == "essay.txt"
        assert model.raw_file_storage_id == "raw_abc123"
        assert model.text_storage_id == "text_def456"
        assert model.file_size_bytes == 1024
        assert model.event == "essay.content.provisioned"
        assert model.content_md5_hash is None
        assert isinstance(model.correlation_id, UUID)
        assert isinstance(model.timestamp, datetime)

    def test_model_serialization(self) -> None:
        """Test EssayContentProvisionedV1 serialization to dict."""
        correlation_id = uuid4()
        model = EssayContentProvisionedV1(
            batch_id="batch_123",
            original_file_name="essay.txt",
            raw_file_storage_id="raw_abc123",
            text_storage_id="text_def456",
            file_size_bytes=1024,
            correlation_id=correlation_id,
        )
        serialized = model.model_dump()
        assert serialized["batch_id"] == "batch_123"
        assert serialized["raw_file_storage_id"] == "raw_abc123"
        assert str(serialized["correlation_id"]) == str(correlation_id)


class TestEssayValidationFailedV1:
    """Test suite for EssayValidationFailedV1 event model."""

    def test_model_creation_with_required_fields(self) -> None:
        """Test that validation failure event can be created with required fields."""
        event = EssayValidationFailedV1(
            batch_id="batch_456",
            original_file_name="empty_essay.txt",
            raw_file_storage_id="raw_xyz789",
            validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
            validation_error_message="File content is empty or contains only whitespace",
            file_size_bytes=0,
        )

        assert event.batch_id == "batch_456"
        assert event.original_file_name == "empty_essay.txt"
        assert event.validation_error_code == FileValidationErrorCode.EMPTY_CONTENT
        assert event.validation_error_message == "File content is empty or contains only whitespace"
        assert event.file_size_bytes == 0
        assert event.event == "essay.validation.failed"
        assert isinstance(event.correlation_id, UUID)
        assert isinstance(event.timestamp, datetime)

    def test_model_with_all_fields(self) -> None:
        """Test validation failure event with all optional fields."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        event = EssayValidationFailedV1(
            batch_id="batch_789",
            original_file_name="too_short_essay.docx",
            raw_file_storage_id="raw_abc456",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_message="Content length (25 characters) below minimum threshold (50)",
            file_size_bytes=512,
            correlation_id=correlation_id,
            timestamp=timestamp,
        )

        assert event.batch_id == "batch_789"
        assert event.validation_error_code == FileValidationErrorCode.CONTENT_TOO_SHORT
        assert event.file_size_bytes == 512
        assert event.correlation_id == correlation_id
        assert event.timestamp == timestamp

    def test_model_serialization_deserialization(self) -> None:
        """Test that validation failure event can be serialized and deserialized."""
        correlation_id = uuid4()
        original_event = EssayValidationFailedV1(
            batch_id="batch_serialize",
            original_file_name="test_file.pdf",
            raw_file_storage_id="raw_serialize123",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_message="Content is too short",
            file_size_bytes=150,
            correlation_id=correlation_id,
        )

        # Serialize to JSON
        json_data = original_event.model_dump_json()
        assert isinstance(json_data, str)

        # Deserialize back to model
        data_dict = json.loads(json_data)
        reconstructed_event = EssayValidationFailedV1.model_validate(data_dict)

        # Verify all fields match
        assert reconstructed_event.batch_id == original_event.batch_id
        assert reconstructed_event.original_file_name == original_event.original_file_name
        assert reconstructed_event.validation_error_code == original_event.validation_error_code
        assert (
            reconstructed_event.validation_error_message == original_event.validation_error_message
        )
        assert reconstructed_event.file_size_bytes == original_event.file_size_bytes
        assert reconstructed_event.correlation_id == original_event.correlation_id

    def test_default_values(self) -> None:
        """Test that default values are properly set."""
        event = EssayValidationFailedV1(
            batch_id="test_batch",
            original_file_name="test.txt",
            raw_file_storage_id="raw_default123",
            validation_error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
            validation_error_message="Test error message",
            file_size_bytes=100,
        )

        # Default event type
        assert event.event == "essay.validation.failed"

        # Default correlation_id
        assert isinstance(event.correlation_id, UUID)

        # Default timestamp (should be recent)
        now = datetime.now(UTC)
        time_diff = abs((now - event.timestamp).total_seconds())
        assert time_diff < 1.0  # Should be within 1 second

    def test_validation_error_code_values(self) -> None:
        """Test event creation with various validation error codes."""
        error_codes = [
            FileValidationErrorCode.EMPTY_CONTENT,
            FileValidationErrorCode.CONTENT_TOO_SHORT,
            FileValidationErrorCode.CONTENT_TOO_LONG,
        ]

        for code in error_codes:
            event = EssayValidationFailedV1(
                batch_id=f"batch_{code.value.lower()}",
                original_file_name=f"test_{code.value.lower()}.txt",
                raw_file_storage_id="raw_test123",
                validation_error_code=code,
                validation_error_message=f"Test {code.value}",
                file_size_bytes=100,
            )
            assert event.validation_error_code == code

    def test_file_size_edge_cases(self) -> None:
        """Test validation failure event with edge case file sizes."""
        # Zero byte file
        event_zero = EssayValidationFailedV1(
            batch_id="batch_zero",
            original_file_name="empty.txt",
            raw_file_storage_id="raw_zero123",
            validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
            validation_error_message="Empty file",
            file_size_bytes=0,
        )
        assert event_zero.file_size_bytes == 0

        # Large file
        event_large = EssayValidationFailedV1(
            batch_id="batch_large",
            original_file_name="huge.txt",
            raw_file_storage_id="raw_large123",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
            validation_error_message="File too large",
            file_size_bytes=10_000_000,
        )
        assert event_large.file_size_bytes == 10_000_000

    def test_timestamp_timezone_handling(self) -> None:
        """Test that timestamps are properly handled with timezone information."""
        # Event with default timestamp
        event_default = EssayValidationFailedV1(
            batch_id="batch_tz",
            original_file_name="test.txt",
            raw_file_storage_id="raw_tz123",
            validation_error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
            validation_error_message="Test message",
            file_size_bytes=100,
        )

        # Should have timezone info
        assert event_default.timestamp.tzinfo is not None
        assert event_default.timestamp.tzinfo == UTC

        # Event with explicit timestamp
        explicit_time = datetime(2025, 1, 16, 12, 0, 0, tzinfo=UTC)
        event_explicit = EssayValidationFailedV1(
            batch_id="batch_explicit",
            original_file_name="test2.txt",
            raw_file_storage_id="raw_explicit123",
            validation_error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
            validation_error_message="Test message",
            file_size_bytes=200,
            timestamp=explicit_time,
        )

        assert event_explicit.timestamp == explicit_time

    def test_model_field_validation(self) -> None:
        """Test that required fields are validated."""
        with pytest.raises(ValueError):
            # Missing required batch_id
            EssayValidationFailedV1(  # type: ignore[call-arg]
                original_file_name="test.txt",
                validation_error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
                validation_error_message="Test message",
                file_size_bytes=100,
            )

    def test_batch_coordination_scenario(self) -> None:
        """Test event creation for realistic batch coordination scenario."""
        # Simulate File Service publishing validation failure for ELS/BOS coordination
        batch_id = "batch_coordination_test"
        correlation_id = uuid4()

        event = EssayValidationFailedV1(
            batch_id=batch_id,
            original_file_name="student_essay_3.docx",
            raw_file_storage_id="raw_coordination123",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_message=(
                "Essay content (15 words) below minimum requirement (50 words)"
            ),
            file_size_bytes=256,
            correlation_id=correlation_id,
        )

        # Verify event contains all information needed for coordination
        assert event.batch_id == batch_id
        assert "student_essay_3.docx" in event.original_file_name
        assert "15 words" in event.validation_error_message
        assert "50 words" in event.validation_error_message
        assert event.validation_error_code == "CONTENT_TOO_SHORT"
        assert event.correlation_id == correlation_id

        # Verify it can be serialized for Kafka publishing
        json_str = event.model_dump_json()
        assert isinstance(json_str, str)
        assert batch_id in json_str
        assert "CONTENT_TOO_SHORT" in json_str
