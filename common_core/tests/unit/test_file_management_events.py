"""
Unit tests for file management event models.

Tests the event models used for enhanced file operations including
student parsing, file additions/removals, and batch management.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Dict
from uuid import UUID, uuid4

import pytest

from common_core.events.file_management_events import (
    BatchFileAddedV1,
    BatchFileRemovedV1,
    StudentParsingCompletedV1,
)


class TestStudentParsingCompletedV1:
    """Test suite for StudentParsingCompletedV1 event model."""

    def test_model_creation_with_required_fields(self) -> None:
        """Test creating StudentParsingCompletedV1 with only required fields."""
        parsing_results = [
            {
                "essay_id": "essay_1",
                "filename": "john_doe.txt",
                "first_name": "John",
                "last_name": "Doe",
                "student_email": "john.doe@student.edu",
                "confidence": 0.95,
            }
        ]

        model = StudentParsingCompletedV1(
            batch_id="batch_123",
            parsing_results=parsing_results,
            parsed_count=1,
            total_count=5,
        )

        assert model.batch_id == "batch_123"
        assert model.parsing_results == parsing_results
        assert model.parsed_count == 1
        assert model.total_count == 5
        assert model.event == "student.parsing.completed"
        assert isinstance(model.correlation_id, UUID)
        assert isinstance(model.timestamp, datetime)

    def test_model_with_all_fields(self) -> None:
        """Test StudentParsingCompletedV1 with all optional fields."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)
        parsing_results = [
            {
                "essay_id": "essay_1",
                "filename": "anna_svensson.docx",
                "first_name": "Anna",
                "last_name": "Svensson",
                "student_email": "anna.svensson@skola.se",
                "confidence": 0.85,
            },
            {
                "essay_id": "essay_2",
                "filename": "erik_johansson.pdf",
                "first_name": "Erik",
                "last_name": "Johansson",
                "student_email": "erik.johansson@skola.se",
                "confidence": 0.92,
            },
        ]

        model = StudentParsingCompletedV1(
            batch_id="batch_456",
            parsing_results=parsing_results,
            parsed_count=2,
            total_count=3,
            correlation_id=correlation_id,
            timestamp=timestamp,
        )

        assert model.batch_id == "batch_456"
        assert model.parsing_results == parsing_results
        assert model.parsed_count == 2
        assert model.total_count == 3
        assert model.correlation_id == correlation_id
        assert model.timestamp == timestamp

    def test_model_serialization_deserialization(self) -> None:
        """Test that student parsing event can be serialized and deserialized."""
        correlation_id = uuid4()
        parsing_results = [
            {
                "essay_id": "essay_serialize",
                "filename": "test_student.txt",
                "first_name": "Test",
                "last_name": "Student",
                "student_email": "test@example.com",
                "confidence": 0.88,
            }
        ]

        original_event = StudentParsingCompletedV1(
            batch_id="batch_serialize",
            parsing_results=parsing_results,
            parsed_count=1,
            total_count=1,
            correlation_id=correlation_id,
        )

        # Serialize to JSON
        json_data = original_event.model_dump_json()
        assert isinstance(json_data, str)

        # Deserialize back to model
        data_dict = json.loads(json_data)
        reconstructed_event = StudentParsingCompletedV1.model_validate(data_dict)

        # Verify all fields match
        assert reconstructed_event.batch_id == original_event.batch_id
        assert reconstructed_event.parsing_results == original_event.parsing_results
        assert reconstructed_event.parsed_count == original_event.parsed_count
        assert reconstructed_event.total_count == original_event.total_count
        assert reconstructed_event.correlation_id == original_event.correlation_id

    def test_empty_parsing_results(self) -> None:
        """Test event with no parsing results."""
        model = StudentParsingCompletedV1(
            batch_id="batch_empty",
            parsing_results=[],
            parsed_count=0,
            total_count=5,
        )

        assert model.parsing_results == []
        assert model.parsed_count == 0
        assert model.total_count == 5

    def test_parsing_results_structure(self) -> None:
        """Test that parsing results maintain expected structure."""
        complex_results: list[Dict[str, Any]] = [
            {
                "essay_id": "essay_complex_1",
                "filename": "maria_andersson_essay.docx",
                "first_name": "Maria",
                "last_name": "Andersson",
                "student_email": "maria.andersson@student.se",
                "confidence": 0.95,
            },
            {
                "essay_id": "essay_complex_2",
                "filename": "unknown_author.txt",
                "first_name": None,
                "last_name": None,
                "student_email": None,
                "confidence": 0.0,
            },
        ]

        model = StudentParsingCompletedV1(
            batch_id="batch_complex",
            parsing_results=complex_results,
            parsed_count=1,
            total_count=2,
        )

        assert len(model.parsing_results) == 2
        assert model.parsing_results[0]["confidence"] == 0.95
        assert model.parsing_results[1]["confidence"] == 0.0


class TestBatchFileAddedV1:
    """Test suite for BatchFileAddedV1 event model."""

    def test_model_creation_with_required_fields(self) -> None:
        """Test creating BatchFileAddedV1 with only required fields."""
        model = BatchFileAddedV1(
            batch_id="batch_123",
            essay_id="essay_456",
            filename="new_essay.txt",
            user_id="user_789",
        )

        assert model.batch_id == "batch_123"
        assert model.essay_id == "essay_456"
        assert model.filename == "new_essay.txt"
        assert model.user_id == "user_789"
        assert model.event == "batch.file.added"
        assert isinstance(model.correlation_id, UUID)
        assert isinstance(model.timestamp, datetime)

    def test_model_with_all_fields(self) -> None:
        """Test BatchFileAddedV1 with all optional fields."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        model = BatchFileAddedV1(
            batch_id="batch_456",
            essay_id="essay_789",
            filename="additional_essay.pdf",
            user_id="teacher_123",
            correlation_id=correlation_id,
            timestamp=timestamp,
        )

        assert model.batch_id == "batch_456"
        assert model.essay_id == "essay_789"
        assert model.filename == "additional_essay.pdf"
        assert model.user_id == "teacher_123"
        assert model.correlation_id == correlation_id
        assert model.timestamp == timestamp

    def test_model_serialization_deserialization(self) -> None:
        """Test that file added event can be serialized and deserialized."""
        correlation_id = uuid4()
        original_event = BatchFileAddedV1(
            batch_id="batch_serialize",
            essay_id="essay_serialize",
            filename="serialize_test.docx",
            user_id="user_serialize",
            correlation_id=correlation_id,
        )

        # Serialize to JSON
        json_data = original_event.model_dump_json()
        assert isinstance(json_data, str)

        # Deserialize back to model
        data_dict = json.loads(json_data)
        reconstructed_event = BatchFileAddedV1.model_validate(data_dict)

        # Verify all fields match
        assert reconstructed_event.batch_id == original_event.batch_id
        assert reconstructed_event.essay_id == original_event.essay_id
        assert reconstructed_event.filename == original_event.filename
        assert reconstructed_event.user_id == original_event.user_id
        assert reconstructed_event.correlation_id == original_event.correlation_id

    def test_real_time_update_scenario(self) -> None:
        """Test event creation for real-time file addition scenario."""
        batch_id = "batch_realtime_test"
        correlation_id = uuid4()

        event = BatchFileAddedV1(
            batch_id=batch_id,
            essay_id="essay_new_addition",
            filename="late_submission.txt",
            user_id="teacher_456",
            correlation_id=correlation_id,
        )

        # Verify event contains all information needed for real-time updates
        assert event.batch_id == batch_id
        assert "late_submission.txt" in event.filename
        assert event.user_id == "teacher_456"
        assert event.correlation_id == correlation_id

        # Verify it can be serialized for Redis pub/sub
        json_str = event.model_dump_json()
        assert isinstance(json_str, str)
        assert batch_id in json_str
        assert "batch.file.added" in json_str


class TestBatchFileRemovedV1:
    """Test suite for BatchFileRemovedV1 event model."""

    def test_model_creation_with_required_fields(self) -> None:
        """Test creating BatchFileRemovedV1 with only required fields."""
        model = BatchFileRemovedV1(
            batch_id="batch_123",
            essay_id="essay_456",
            filename="removed_essay.txt",
            user_id="user_789",
        )

        assert model.batch_id == "batch_123"
        assert model.essay_id == "essay_456"
        assert model.filename == "removed_essay.txt"
        assert model.user_id == "user_789"
        assert model.event == "batch.file.removed"
        assert isinstance(model.correlation_id, UUID)
        assert isinstance(model.timestamp, datetime)

    def test_model_with_all_fields(self) -> None:
        """Test BatchFileRemovedV1 with all optional fields."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        model = BatchFileRemovedV1(
            batch_id="batch_456",
            essay_id="essay_789",
            filename="unwanted_essay.pdf",
            user_id="teacher_123",
            correlation_id=correlation_id,
            timestamp=timestamp,
        )

        assert model.batch_id == "batch_456"
        assert model.essay_id == "essay_789"
        assert model.filename == "unwanted_essay.pdf"
        assert model.user_id == "teacher_123"
        assert model.correlation_id == correlation_id
        assert model.timestamp == timestamp

    def test_model_serialization_deserialization(self) -> None:
        """Test that file removed event can be serialized and deserialized."""
        correlation_id = uuid4()
        original_event = BatchFileRemovedV1(
            batch_id="batch_remove_serialize",
            essay_id="essay_remove_serialize",
            filename="remove_test.docx",
            user_id="user_remove_serialize",
            correlation_id=correlation_id,
        )

        # Serialize to JSON
        json_data = original_event.model_dump_json()
        assert isinstance(json_data, str)

        # Deserialize back to model
        data_dict = json.loads(json_data)
        reconstructed_event = BatchFileRemovedV1.model_validate(data_dict)

        # Verify all fields match
        assert reconstructed_event.batch_id == original_event.batch_id
        assert reconstructed_event.essay_id == original_event.essay_id
        assert reconstructed_event.filename == original_event.filename
        assert reconstructed_event.user_id == original_event.user_id
        assert reconstructed_event.correlation_id == original_event.correlation_id

    def test_file_removal_workflow_scenario(self) -> None:
        """Test event creation for file removal workflow scenario."""
        batch_id = "batch_removal_workflow"
        correlation_id = uuid4()

        event = BatchFileRemovedV1(
            batch_id=batch_id,
            essay_id="essay_incorrect_upload",
            filename="wrong_assignment.pdf",
            user_id="teacher_correcting",
            correlation_id=correlation_id,
        )

        # Verify event contains all information needed for workflow coordination
        assert event.batch_id == batch_id
        assert "wrong_assignment.pdf" in event.filename
        assert event.user_id == "teacher_correcting"
        assert event.correlation_id == correlation_id

        # Verify it can be serialized for Kafka/Redis publishing
        json_str = event.model_dump_json()
        assert isinstance(json_str, str)
        assert batch_id in json_str
        assert "batch.file.removed" in json_str

    def test_field_validation(self) -> None:
        """Test that required fields are validated for file management events."""
        with pytest.raises(ValueError):
            # Missing required batch_id for file added
            BatchFileAddedV1(  # type: ignore[call-arg]
                essay_id="essay_test",
                filename="test.txt",
                user_id="user_test",
            )

        with pytest.raises(ValueError):
            # Missing required user_id for file removed
            BatchFileRemovedV1(  # type: ignore[call-arg]
                batch_id="batch_test",
                essay_id="essay_test",
                filename="test.txt",
            )

    def test_timestamp_consistency(self) -> None:
        """Test timestamp handling across file management events."""
        file_added_event = BatchFileAddedV1(
            batch_id="batch_time",
            essay_id="essay_time_1",
            filename="time_test_1.txt",
            user_id="user_time",
        )
        file_removed_event = BatchFileRemovedV1(
            batch_id="batch_time",
            essay_id="essay_time_2",
            filename="time_test_2.txt",
            user_id="user_time",
        )

        # Test file added event timestamp
        assert file_added_event.timestamp.tzinfo is not None
        assert file_added_event.timestamp.tzinfo == UTC
        now = datetime.now(UTC)
        time_diff = abs((now - file_added_event.timestamp).total_seconds())
        assert time_diff < 1.0  # Should be within 1 second

        # Test file removed event timestamp
        assert file_removed_event.timestamp.tzinfo is not None
        assert file_removed_event.timestamp.tzinfo == UTC
        time_diff = abs((now - file_removed_event.timestamp).total_seconds())
        assert time_diff < 1.0  # Should be within 1 second
