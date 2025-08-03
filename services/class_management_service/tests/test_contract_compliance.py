"""
Contract tests for event publishing and data model compliance.

Tests serialization/deserialization round-trips for EventEnvelope patterns
and validates Pydantic model contracts per HuleEdu testing standards.
"""

from __future__ import annotations

import uuid

import pytest
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.class_events import (
    ClassCreatedV1,
    ClassUpdatedV1,
    StudentCreatedV1,
    StudentUpdatedV1,
)
from common_core.events.envelope import EventEnvelope


class TestEventContractCompliance:
    """Test suite for event contract compliance and serialization."""

    def test_event_envelope_class_created_round_trip(self) -> None:
        """Test ClassCreatedV1 event serialization/deserialization round-trip."""
        # Arrange
        original_data = ClassCreatedV1(
            class_id=str(uuid.uuid4()),
            class_designation="Advanced English",
            course_codes=[CourseCode.ENG5],
            user_id="test-teacher",
        )

        original_envelope = EventEnvelope[ClassCreatedV1](
            event_type=topic_name(ProcessingEvent.CLASS_CREATED),
            source_service="class_management_service",
            correlation_id=uuid.uuid4(),
            data=original_data,
        )

        # Act - serialize and deserialize using established EventEnvelope pattern
        serialized = original_envelope.model_dump_json()
        reconstructed_envelope = EventEnvelope[ClassCreatedV1].model_validate_json(serialized)
        typed_data = ClassCreatedV1.model_validate(reconstructed_envelope.data)

        # Assert - round-trip integrity
        assert reconstructed_envelope.event_type == original_envelope.event_type
        assert reconstructed_envelope.source_service == original_envelope.source_service
        assert reconstructed_envelope.correlation_id == original_envelope.correlation_id
        assert typed_data.class_id == original_data.class_id
        assert typed_data.class_designation == original_data.class_designation
        assert typed_data.course_codes == original_data.course_codes
        assert typed_data.user_id == original_data.user_id

    def test_event_envelope_class_updated_round_trip(self) -> None:
        """Test ClassUpdatedV1 event serialization/deserialization round-trip."""
        # Arrange
        original_data = ClassUpdatedV1(
            class_id=str(uuid.uuid4()),
            class_designation="Updated Class Name",
            course_codes=[CourseCode.SV1],
            user_id="test-teacher",
        )

        original_envelope = EventEnvelope[ClassUpdatedV1](
            event_type=topic_name(ProcessingEvent.CLASS_UPDATED),
            source_service="class_management_service",
            correlation_id=uuid.uuid4(),
            data=original_data,
        )

        # Act - serialize and deserialize using established EventEnvelope pattern
        serialized = original_envelope.model_dump_json()
        reconstructed_envelope = EventEnvelope[ClassUpdatedV1].model_validate_json(serialized)
        typed_data = ClassUpdatedV1.model_validate(reconstructed_envelope.data)

        # Assert - round-trip integrity
        assert typed_data.class_id == original_data.class_id
        assert typed_data.class_designation == original_data.class_designation
        assert typed_data.course_codes == original_data.course_codes
        assert reconstructed_envelope.correlation_id == original_envelope.correlation_id

    def test_event_envelope_student_created_round_trip(self) -> None:
        """Test StudentCreatedV1 event serialization/deserialization round-trip."""
        # Arrange
        original_data = StudentCreatedV1(
            student_id=str(uuid.uuid4()),
            first_name="Jane",
            last_name="Smith",
            student_email="jane.smith@example.com",
            class_ids=[],
            created_by_user_id="test-teacher",
        )

        original_envelope = EventEnvelope[StudentCreatedV1](
            event_type=topic_name(ProcessingEvent.STUDENT_CREATED),
            source_service="class_management_service",
            correlation_id=uuid.uuid4(),
            data=original_data,
        )

        # Act - serialize and deserialize using established EventEnvelope pattern
        serialized = original_envelope.model_dump_json()
        reconstructed_envelope = EventEnvelope[StudentCreatedV1].model_validate_json(serialized)
        typed_data = StudentCreatedV1.model_validate(reconstructed_envelope.data)

        # Assert - round-trip integrity
        assert typed_data.student_id == original_data.student_id
        assert typed_data.first_name == original_data.first_name
        assert typed_data.last_name == original_data.last_name
        assert typed_data.student_email == original_data.student_email
        assert typed_data.created_by_user_id == original_data.created_by_user_id

    def test_event_envelope_student_updated_round_trip(self) -> None:
        """Test StudentUpdatedV1 event serialization/deserialization round-trip."""
        # Arrange
        original_data = StudentUpdatedV1(
            student_id=str(uuid.uuid4()),
            first_name="John",
            last_name="Updated",
            student_email="john.updated@example.com",
            add_class_ids=None,
            remove_class_ids=None,
            updated_by_user_id="test-teacher",
        )

        original_envelope = EventEnvelope[StudentUpdatedV1](
            event_type=topic_name(ProcessingEvent.STUDENT_UPDATED),
            source_service="class_management_service",
            correlation_id=uuid.uuid4(),
            data=original_data,
        )

        # Act - serialize and deserialize using established EventEnvelope pattern
        serialized = original_envelope.model_dump_json()
        reconstructed_envelope = EventEnvelope[StudentUpdatedV1].model_validate_json(serialized)
        typed_data = StudentUpdatedV1.model_validate(reconstructed_envelope.data)

        # Assert - round-trip integrity
        assert typed_data.student_id == original_data.student_id
        assert typed_data.first_name == original_data.first_name
        assert typed_data.last_name == original_data.last_name
        assert typed_data.student_email == original_data.student_email

    def test_event_envelope_correlation_id_propagation(self) -> None:
        """Test correlation ID propagates correctly through event processing."""
        # Arrange
        test_correlation_id = uuid.uuid4()

        # Test with different event types to ensure pattern consistency
        class_event = EventEnvelope[ClassCreatedV1](
            event_type=topic_name(ProcessingEvent.CLASS_CREATED),
            source_service="class_management_service",
            correlation_id=test_correlation_id,
            data=ClassCreatedV1(
                class_id=str(uuid.uuid4()),
                class_designation="Test Class",
                course_codes=[CourseCode.ENG5],
                user_id="test-user",
            ),
        )

        student_event = EventEnvelope[StudentCreatedV1](
            event_type=topic_name(ProcessingEvent.STUDENT_CREATED),
            source_service="class_management_service",
            correlation_id=test_correlation_id,  # Same correlation ID
            data=StudentCreatedV1(
                student_id=str(uuid.uuid4()),
                first_name="Test",
                last_name="Student",
                student_email="test@example.com",
                class_ids=[],
                created_by_user_id="test-user",
            ),
        )

        # Assert - correlation ID consistency
        assert class_event.correlation_id == test_correlation_id
        assert student_event.correlation_id == test_correlation_id
        assert class_event.correlation_id == student_event.correlation_id

    def test_event_schema_validation_required_fields(self) -> None:
        """Test that required fields are validated in event schemas."""
        # Test ClassCreatedV1 required fields
        with pytest.raises(ValueError):
            ClassCreatedV1(
                # Missing class_id - intentionally omitted
                class_designation="Test Class",
                course_codes=[CourseCode.ENG5],
                user_id="test-user",
            )  # type: ignore[call-arg]

        with pytest.raises(ValueError):
            ClassCreatedV1(
                class_id=str(uuid.uuid4()),
                # Missing class_designation - intentionally omitted
                course_codes=[CourseCode.ENG5],
                user_id="test-user",
            )  # type: ignore[call-arg]

    def test_event_data_type_validation(self) -> None:
        """Test event data type validation for correct types."""
        # Test that course_codes accepts CourseCode enums
        valid_event = ClassCreatedV1(
            class_id=str(uuid.uuid4()),
            class_designation="Test Class",
            course_codes=[CourseCode.ENG5, CourseCode.SV1],  # Multiple courses
            user_id="test-user",
        )

        assert len(valid_event.course_codes) == 2
        assert CourseCode.ENG5 in valid_event.course_codes
        assert CourseCode.SV1 in valid_event.course_codes

    def test_event_envelope_metadata_validation(self) -> None:
        """Test EventEnvelope metadata fields are correctly validated."""
        # Arrange
        test_data = ClassCreatedV1(
            class_id=str(uuid.uuid4()),
            class_designation="Test Class",
            course_codes=[CourseCode.ENG5],
            user_id="test-user",
        )

        # Act & Assert - valid envelope
        valid_envelope = EventEnvelope[ClassCreatedV1](
            event_type=topic_name(ProcessingEvent.CLASS_CREATED),
            source_service="class_management_service",
            correlation_id=uuid.uuid4(),
            data=test_data,
        )

        # Verify envelope structure
        assert valid_envelope.event_id is not None
        assert valid_envelope.event_timestamp is not None
        assert valid_envelope.event_type == topic_name(ProcessingEvent.CLASS_CREATED)
        assert valid_envelope.source_service == "class_management_service"
        assert valid_envelope.correlation_id is not None
        assert valid_envelope.data == test_data

    def test_json_serialization_compatibility(self) -> None:
        """Test that events can be serialized to JSON for Kafka compatibility."""
        # Arrange
        event_data = ClassCreatedV1(
            class_id=str(uuid.uuid4()),
            class_designation="JSON Test Class",
            course_codes=[CourseCode.ENG5],
            user_id="test-user",
        )

        envelope = EventEnvelope[ClassCreatedV1](
            event_type=topic_name(ProcessingEvent.CLASS_CREATED),
            source_service="class_management_service",
            correlation_id=uuid.uuid4(),
            data=event_data,
        )

        # Act - serialize to JSON
        json_str = envelope.model_dump_json()

        # Assert - JSON is valid and contains expected data
        assert isinstance(json_str, str)
        assert "class_id" in json_str
        assert "JSON Test Class" in json_str
        assert "ENG5" in json_str
        assert "class_management_service" in json_str

        # Verify we can deserialize back using established EventEnvelope pattern
        reconstructed_envelope = EventEnvelope[ClassCreatedV1].model_validate_json(json_str)
        typed_data = ClassCreatedV1.model_validate(reconstructed_envelope.data)
        assert typed_data.class_designation == "JSON Test Class"

    def test_event_schema_backward_compatibility(self) -> None:
        """Test that event schemas maintain backward compatibility."""
        # This test ensures that existing event consumers won't break
        # when new optional fields are added to event schemas

        # Simulate an older event payload that might be missing new optional fields
        minimal_class_event_data = {
            "class_id": str(uuid.uuid4()),
            "class_designation": "Minimal Class",
            "course_codes": ["ENG5"],
            "user_id": "test-user",
        }

        # This should not raise an error even if new optional fields are added later
        event = ClassCreatedV1.model_validate(minimal_class_event_data)
        assert event.class_designation == "Minimal Class"
        assert event.course_codes == [CourseCode.ENG5]
