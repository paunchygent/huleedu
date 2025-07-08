"""
Unit tests for common_core.events.utils module.

Tests the deterministic event ID generation utility that is critical
for idempotency guarantees in the HuleEdu platform.
"""

import json
from uuid import uuid4

import pytest
from huleedu_service_libs.event_utils import (
    extract_correlation_id_from_event,
    generate_deterministic_event_id,
)


class TestGenerateDeterministicEventId:
    """Test cases for deterministic event ID generation."""

    def test_identical_data_produces_same_id(self) -> None:
        """Test that identical data payloads produce identical deterministic IDs."""
        # Arrange
        event_data = {
            "data": {"batch_id": "batch_123", "essay_count": 5, "status": "completed"},
            "event_id": str(uuid4()),  # Different each time
            "event_timestamp": "2024-01-15T10:30:00Z",  # Different each time
            "source_service": "batch_orchestrator_service",
        }

        # Create two identical events with different transient metadata
        event1 = event_data.copy()
        event1["event_id"] = str(uuid4())
        event1["event_timestamp"] = "2024-01-15T10:30:00Z"

        event2 = event_data.copy()
        event2["event_id"] = str(uuid4())  # Different UUID
        event2["event_timestamp"] = "2024-01-15T10:31:00Z"  # Different timestamp

        msg1 = json.dumps(event1).encode("utf-8")
        msg2 = json.dumps(event2).encode("utf-8")

        # Act
        id1 = generate_deterministic_event_id(msg1)
        id2 = generate_deterministic_event_id(msg2)

        # Assert
        assert id1 == id2, "Identical data should produce identical deterministic IDs"
        assert len(id1) == 64, "SHA256 hash should be 64 characters"

    def test_different_data_produces_different_ids(self) -> None:
        """Test that different data payloads produce different deterministic IDs."""
        # Arrange
        event1 = {
            "data": {"batch_id": "batch_123", "status": "completed"},
            "event_id": str(uuid4()),
        }

        event2 = {
            "data": {"batch_id": "batch_456", "status": "completed"},  # Different batch_id
            "event_id": str(uuid4()),
        }

        msg1 = json.dumps(event1).encode("utf-8")
        msg2 = json.dumps(event2).encode("utf-8")

        # Act
        id1 = generate_deterministic_event_id(msg1)
        id2 = generate_deterministic_event_id(msg2)

        # Assert
        assert id1 != id2, "Different data should produce different deterministic IDs"

    def test_key_order_independence(self) -> None:
        """Test that JSON key order doesn't affect the deterministic ID."""
        # Arrange
        event1 = {
            "data": {"batch_id": "123", "essay_count": 5, "status": "completed"},
            "event_id": str(uuid4()),
        }

        event2 = {
            "data": {"status": "completed", "batch_id": "123", "essay_count": 5},  # Different order
            "event_id": str(uuid4()),
        }

        msg1 = json.dumps(event1).encode("utf-8")
        msg2 = json.dumps(event2).encode("utf-8")

        # Act
        id1 = generate_deterministic_event_id(msg1)
        id2 = generate_deterministic_event_id(msg2)

        # Assert
        assert id1 == id2, "Key order should not affect deterministic ID"

    def test_nested_data_consistency(self) -> None:
        """Test deterministic ID generation with nested data structures."""
        # Arrange
        event1 = {
            "data": {
                "batch_id": "123",
                "metadata": {"source": "file_service", "version": "1.0"},
                "essays": [{"id": "essay_1"}, {"id": "essay_2"}],
            },
        }

        event2 = {
            "data": {
                "essays": [{"id": "essay_1"}, {"id": "essay_2"}],  # Same data, different order
                "batch_id": "123",
                "metadata": {"version": "1.0", "source": "file_service"},
            },
        }

        msg1 = json.dumps(event1).encode("utf-8")
        msg2 = json.dumps(event2).encode("utf-8")

        # Act
        id1 = generate_deterministic_event_id(msg1)
        id2 = generate_deterministic_event_id(msg2)

        # Assert
        assert id1 == id2, "Nested data with same content should produce identical IDs"

    def test_empty_data_field(self) -> None:
        """Test handling of events with empty data field."""
        # Arrange
        event = {"data": {}, "event_id": str(uuid4()), "source_service": "test_service"}

        msg = json.dumps(event).encode("utf-8")

        # Act
        result_id = generate_deterministic_event_id(msg)

        # Assert
        assert isinstance(result_id, str), "Should return a string ID"
        assert len(result_id) == 64, "Should return valid SHA256 hash"

    def test_missing_data_field_raises_error(self) -> None:
        """Test that missing data field raises ValueError."""
        # Arrange
        event = {
            "event_id": str(uuid4()),
            "source_service": "test_service",
            # No 'data' field
        }

        msg = json.dumps(event).encode("utf-8")

        # Act & Assert
        with pytest.raises(ValueError, match="Event message must contain a 'data' field"):
            generate_deterministic_event_id(msg)

    def test_malformed_json_raises_error(self) -> None:
        """Test that malformed JSON raises ValueError."""
        # Arrange
        malformed_msg = b'{"invalid": json syntax'

        # Act & Assert
        with pytest.raises(ValueError, match="Failed to decode or process event message"):
            generate_deterministic_event_id(malformed_msg)

    def test_non_utf8_bytes_raises_error(self) -> None:
        """Test that non-UTF8 bytes raise ValueError."""
        # Arrange
        non_utf8_msg = b"\xff\xfe\x00\x00invalid_bytes"

        # Act & Assert
        with pytest.raises((ValueError, UnicodeDecodeError)):
            generate_deterministic_event_id(non_utf8_msg)

    def test_real_world_event_structure(self) -> None:
        """Test with realistic HuleEdu event structure."""
        # Arrange - Based on actual EssayContentProvisionedV1 event
        event = {
            "event_id": str(uuid4()),
            "event_type": "huleedu.essay.content.provisioned.v1",
            "event_timestamp": "2024-01-15T10:30:00Z",
            "source_service": "file_service",
            "correlation_id": str(uuid4()),
            "data": {
                "batch_id": "batch_abc123",
                "essay_id": "essay_def456",
                "raw_file_storage_id": "raw_storage_789",
                "text_storage_id": "text_storage_101",
                "student_metadata": {
                    "student_name": "John Doe",
                    "student_email": "john@example.com",
                },
            },
        }

        msg = json.dumps(event).encode("utf-8")

        # Act
        result_id = generate_deterministic_event_id(msg)

        # Assert
        assert isinstance(result_id, str), "Should return a string ID"
        assert len(result_id) == 64, "Should return valid SHA256 hash"


class TestExtractCorrelationIdFromEvent:
    """Test cases for correlation ID extraction."""

    def test_extract_existing_correlation_id(self) -> None:
        """Test extracting correlation ID when it exists."""
        # Arrange
        correlation_id = str(uuid4())
        event = {
            "event_id": str(uuid4()),
            "correlation_id": correlation_id,
            "data": {"batch_id": "123"},
        }

        msg = json.dumps(event).encode("utf-8")

        # Act
        result = extract_correlation_id_from_event(msg)

        # Assert
        assert result == correlation_id

    def test_extract_missing_correlation_id(self) -> None:
        """Test behavior when correlation ID is missing."""
        # Arrange
        event = {
            "event_id": str(uuid4()),
            "data": {"batch_id": "123"},
            # No correlation_id field
        }

        msg = json.dumps(event).encode("utf-8")

        # Act
        result = extract_correlation_id_from_event(msg)

        # Assert
        assert result is None

    def test_extract_from_malformed_json(self) -> None:
        """Test behavior with malformed JSON."""
        # Arrange
        malformed_msg = b'{"invalid": json'

        # Act
        result = extract_correlation_id_from_event(malformed_msg)

        # Assert
        assert result is None
