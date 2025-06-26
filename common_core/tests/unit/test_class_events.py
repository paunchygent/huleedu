"""
Unit tests for class management event models.

Tests the event models used for class creation, student management,
and essay-student associations in the class management system.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from common_core.domain_enums import CourseCode
from common_core.events.class_events import (
    ClassCreatedV1,
    EssayStudentAssociationUpdatedV1,
    StudentCreatedV1,
)


class TestClassCreatedV1:
    """Test suite for ClassCreatedV1 event model."""

    def test_model_creation_with_required_fields(self) -> None:
        """Test creating ClassCreatedV1 with only required fields."""
        model = ClassCreatedV1(
            class_id="class_123",
            class_designation="9A English",
            course_codes=[CourseCode.ENG5, CourseCode.ENG6],
            user_id="teacher_456",
        )

        assert model.class_id == "class_123"
        assert model.class_designation == "9A English"
        assert model.course_codes == [CourseCode.ENG5, CourseCode.ENG6]
        assert model.user_id == "teacher_456"
        assert model.event == "class.created"
        assert model.correlation_id is None
        assert isinstance(model.timestamp, datetime)

    def test_model_with_all_fields(self) -> None:
        """Test ClassCreatedV1 with all optional fields."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        model = ClassCreatedV1(
            class_id="class_456",
            class_designation="8B Svenska",
            course_codes=[CourseCode.SV1, CourseCode.SV2],
            user_id="teacher_789",
            correlation_id=correlation_id,
            timestamp=timestamp,
        )

        assert model.class_id == "class_456"
        assert model.class_designation == "8B Svenska"
        assert model.course_codes == [CourseCode.SV1, CourseCode.SV2]
        assert model.user_id == "teacher_789"
        assert model.correlation_id == correlation_id
        assert model.timestamp == timestamp

    def test_model_serialization_deserialization(self) -> None:
        """Test that class created event can be serialized and deserialized."""
        correlation_id = uuid4()
        original_event = ClassCreatedV1(
            class_id="class_serialize",
            class_designation="Test Class Serialization",
            course_codes=[CourseCode.ENG7],
            user_id="teacher_serialize",
            correlation_id=correlation_id,
        )

        # Serialize to JSON
        json_data = original_event.model_dump_json()
        assert isinstance(json_data, str)

        # Deserialize back to model
        data_dict = json.loads(json_data)
        reconstructed_event = ClassCreatedV1.model_validate(data_dict)

        # Verify all fields match
        assert reconstructed_event.class_id == original_event.class_id
        assert reconstructed_event.class_designation == original_event.class_designation
        assert reconstructed_event.course_codes == original_event.course_codes
        assert reconstructed_event.user_id == original_event.user_id
        assert reconstructed_event.correlation_id == original_event.correlation_id

    def test_multiple_course_codes(self) -> None:
        """Test class creation with multiple course codes."""
        model = ClassCreatedV1(
            class_id="class_multi",
            class_designation="Advanced English Writing",
            course_codes=[CourseCode.ENG5, CourseCode.ENG6, CourseCode.ENG7],
            user_id="teacher_multi",
        )

        assert len(model.course_codes) == 3
        assert CourseCode.ENG5 in model.course_codes
        assert CourseCode.ENG6 in model.course_codes
        assert CourseCode.ENG7 in model.course_codes

    def test_single_course_code(self) -> None:
        """Test class creation with single course code."""
        model = ClassCreatedV1(
            class_id="class_single",
            class_designation="Beginner Swedish",
            course_codes=[CourseCode.SV1],
            user_id="teacher_single",
        )

        assert len(model.course_codes) == 1
        assert model.course_codes[0] == CourseCode.SV1


class TestStudentCreatedV1:
    """Test suite for StudentCreatedV1 event model."""

    def test_model_creation_with_required_fields(self) -> None:
        """Test creating StudentCreatedV1 with only required fields."""
        model = StudentCreatedV1(
            student_id="student_123",
            first_name="Anna",
            last_name="Svensson",
            student_email="anna.svensson@skola.se",
            class_ids=["class_456"],
            created_by_user_id="teacher_789",
        )

        assert model.student_id == "student_123"
        assert model.first_name == "Anna"
        assert model.last_name == "Svensson"
        assert model.student_email == "anna.svensson@skola.se"
        assert model.class_ids == ["class_456"]
        assert model.created_by_user_id == "teacher_789"
        assert model.event == "student.created"
        assert model.correlation_id is None
        assert isinstance(model.timestamp, datetime)

    def test_model_with_all_fields(self) -> None:
        """Test StudentCreatedV1 with all optional fields."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        model = StudentCreatedV1(
            student_id="student_456",
            first_name="Erik",
            last_name="Johansson",
            student_email="erik.johansson@student.edu",
            class_ids=["class_789", "class_012"],
            created_by_user_id="teacher_345",
            correlation_id=correlation_id,
            timestamp=timestamp,
        )

        assert model.student_id == "student_456"
        assert model.first_name == "Erik"
        assert model.last_name == "Johansson"
        assert model.student_email == "erik.johansson@student.edu"
        assert model.class_ids == ["class_789", "class_012"]
        assert model.created_by_user_id == "teacher_345"
        assert model.correlation_id == correlation_id
        assert model.timestamp == timestamp

    def test_model_serialization_deserialization(self) -> None:
        """Test that student created event can be serialized and deserialized."""
        correlation_id = uuid4()
        original_event = StudentCreatedV1(
            student_id="student_serialize",
            first_name="Test",
            last_name="Student",
            student_email="test.student@example.com",
            class_ids=["class_test"],
            created_by_user_id="teacher_test",
            correlation_id=correlation_id,
        )

        # Serialize to JSON
        json_data = original_event.model_dump_json()
        assert isinstance(json_data, str)

        # Deserialize back to model
        data_dict = json.loads(json_data)
        reconstructed_event = StudentCreatedV1.model_validate(data_dict)

        # Verify all fields match
        assert reconstructed_event.student_id == original_event.student_id
        assert reconstructed_event.first_name == original_event.first_name
        assert reconstructed_event.last_name == original_event.last_name
        assert reconstructed_event.student_email == original_event.student_email
        assert reconstructed_event.class_ids == original_event.class_ids
        assert reconstructed_event.created_by_user_id == original_event.created_by_user_id
        assert reconstructed_event.correlation_id == original_event.correlation_id

    def test_multiple_class_associations(self) -> None:
        """Test student creation with multiple class associations."""
        model = StudentCreatedV1(
            student_id="student_multi_class",
            first_name="Maria",
            last_name="Andersson",
            student_email="maria.andersson@school.se",
            class_ids=["class_eng5", "class_eng6", "class_sv1"],
            created_by_user_id="teacher_multi",
        )

        assert len(model.class_ids) == 3
        assert "class_eng5" in model.class_ids
        assert "class_eng6" in model.class_ids
        assert "class_sv1" in model.class_ids

    def test_swedish_name_patterns(self) -> None:
        """Test student creation with Swedish naming patterns."""
        model = StudentCreatedV1(
            student_id="student_swedish",
            first_name="Lars-Erik",
            last_name="Svensson-Andersson",
            student_email="lars.erik@gymnasium.se",
            class_ids=["class_sv_advanced"],
            created_by_user_id="teacher_swedish",
        )

        assert model.first_name == "Lars-Erik"
        assert model.last_name == "Svensson-Andersson"
        assert model.student_email is not None  # Ensure it's not None before checking substring
        assert "gymnasium.se" in model.student_email


class TestEssayStudentAssociationUpdatedV1:
    """Test suite for EssayStudentAssociationUpdatedV1 event model."""

    def test_model_creation_with_required_fields(self) -> None:
        """Test creating EssayStudentAssociationUpdatedV1 with only required fields."""
        model = EssayStudentAssociationUpdatedV1(
            batch_id="batch_123",
            essay_id="essay_456",
            student_id="student_789",
            first_name="Anna",
            last_name="Andersson",
            student_email="anna.andersson@school.se",
            association_method="manual",
            confidence_score=None,
            created_by_user_id="teacher_012",
        )

        assert model.batch_id == "batch_123"
        assert model.essay_id == "essay_456"
        assert model.student_id == "student_789"
        assert model.first_name == "Anna"
        assert model.last_name == "Andersson"
        assert model.student_email == "anna.andersson@school.se"
        assert model.association_method == "manual"
        assert model.created_by_user_id == "teacher_012"
        assert model.event == "essay.student.association.updated"
        assert model.confidence_score is None
        assert model.correlation_id is None
        assert isinstance(model.timestamp, datetime)

    def test_model_with_parsed_association(self) -> None:
        """Test association event for parsed (automatic) association."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        model = EssayStudentAssociationUpdatedV1(
            batch_id="batch_parsed",
            essay_id="essay_parsed",
            student_id="student_parsed",
            first_name="Erik",
            last_name="Johansson",
            student_email="erik.johansson@skola.se",
            association_method="parsed",
            confidence_score=0.92,
            created_by_user_id="teacher_parsed",
            correlation_id=correlation_id,
            timestamp=timestamp,
        )

        assert model.batch_id == "batch_parsed"
        assert model.association_method == "parsed"
        assert model.confidence_score == 0.92
        assert model.correlation_id == correlation_id
        assert model.timestamp == timestamp

    def test_model_with_association_removal(self) -> None:
        """Test association event for removing student association."""
        model = EssayStudentAssociationUpdatedV1(
            batch_id="batch_removal",
            essay_id="essay_removal",
            student_id=None,  # None indicates removal
            first_name=None,
            last_name=None,
            student_email=None,
            association_method="manual",
            confidence_score=None,
            created_by_user_id="teacher_removal",
        )

        assert model.batch_id == "batch_removal"
        assert model.student_id is None
        assert model.first_name is None
        assert model.last_name is None
        assert model.student_email is None
        assert model.association_method == "manual"

    def test_model_serialization_deserialization(self) -> None:
        """Test that association event can be serialized and deserialized."""
        correlation_id = uuid4()
        original_event = EssayStudentAssociationUpdatedV1(
            batch_id="batch_serialize_assoc",
            essay_id="essay_serialize_assoc",
            student_id="student_serialize_assoc",
            first_name="Test",
            last_name="Association",
            student_email="test.association@example.com",
            association_method="parsed",
            confidence_score=0.85,
            created_by_user_id="teacher_serialize_assoc",
            correlation_id=correlation_id,
        )

        # Serialize to JSON
        json_data = original_event.model_dump_json()
        assert isinstance(json_data, str)

        # Deserialize back to model
        data_dict = json.loads(json_data)
        reconstructed_event = EssayStudentAssociationUpdatedV1.model_validate(data_dict)

        # Verify all fields match
        assert reconstructed_event.batch_id == original_event.batch_id
        assert reconstructed_event.essay_id == original_event.essay_id
        assert reconstructed_event.student_id == original_event.student_id
        assert reconstructed_event.first_name == original_event.first_name
        assert reconstructed_event.last_name == original_event.last_name
        assert reconstructed_event.student_email == original_event.student_email
        assert reconstructed_event.association_method == original_event.association_method
        assert reconstructed_event.confidence_score == original_event.confidence_score
        assert reconstructed_event.created_by_user_id == original_event.created_by_user_id
        assert reconstructed_event.correlation_id == original_event.correlation_id

    def test_confidence_score_ranges(self) -> None:
        """Test association events with various confidence score values."""
        # High confidence
        high_confidence_event = EssayStudentAssociationUpdatedV1(
            batch_id="batch_high_conf",
            essay_id="essay_high_conf",
            student_id="student_high_conf",
            first_name="High",
            last_name="Confidence",
            student_email="high.confidence@test.com",
            association_method="parsed",
            confidence_score=0.98,
            created_by_user_id="teacher_high_conf",
        )
        assert high_confidence_event.confidence_score == 0.98

        # Low confidence
        low_confidence_event = EssayStudentAssociationUpdatedV1(
            batch_id="batch_low_conf",
            essay_id="essay_low_conf",
            student_id="student_low_conf",
            first_name="Low",
            last_name="Confidence",
            student_email="low.confidence@test.com",
            association_method="parsed",
            confidence_score=0.15,
            created_by_user_id="teacher_low_conf",
        )
        assert low_confidence_event.confidence_score == 0.15

        # No confidence (manual association)
        manual_event = EssayStudentAssociationUpdatedV1(
            batch_id="batch_manual",
            essay_id="essay_manual",
            student_id="student_manual",
            first_name="Manual",
            last_name="Association",
            student_email="manual.association@test.com",
            association_method="manual",
            confidence_score=None,
            created_by_user_id="teacher_manual",
        )
        assert manual_event.confidence_score is None

    def test_field_validation(self) -> None:
        """Test that required fields are validated for class management events."""
        with pytest.raises(ValueError):
            # Missing required batch_id for class created
            ClassCreatedV1(  # type: ignore[call-arg]
                class_designation="Test Class",
                course_codes=[CourseCode.ENG5],
                user_id="teacher_test",
            )

        with pytest.raises(ValueError):
            # Missing required first_name for student created
            StudentCreatedV1(  # type: ignore[call-arg]
                student_id="student_test",
                last_name="Test",
                student_email="test@example.com",
                class_ids=["class_test"],
                created_by_user_id="teacher_test",
            )

        with pytest.raises(ValueError):
            # Missing required created_by_user_id for association
            EssayStudentAssociationUpdatedV1(  # type: ignore[call-arg]
                batch_id="batch_test",
                essay_id="essay_test",
                student_id="student_test",
                first_name="Test",
                last_name="Student",
                student_email="test@example.com",
                association_method="manual",
                confidence_score=None,
            )

    def test_real_world_workflow_scenarios(self) -> None:
        """Test events in realistic class management workflow scenarios."""
        # Scenario 1: Teacher creates a new class
        class_event = ClassCreatedV1(
            class_id="class_workflow_2025",
            class_designation="9A English Writing 2025",
            course_codes=[CourseCode.ENG5, CourseCode.ENG6],
            user_id="teacher_workflow",
        )

        # Scenario 2: Teacher adds students to the class
        student_event = StudentCreatedV1(
            student_id="student_workflow_1",
            first_name="Emma",
            last_name="Lindström",
            student_email="emma.lindstrom@school.se",
            class_ids=["class_workflow_2025"],
            created_by_user_id="teacher_workflow",
        )

        # Scenario 3: Automatic parsing associates essay with student
        association_event = EssayStudentAssociationUpdatedV1(
            batch_id="batch_workflow_2025_spring",
            essay_id="essay_emma_narrative",
            student_id="student_workflow_1",
            first_name="Emma",
            last_name="Lindström",
            student_email="emma.lindstrom@school.se",
            association_method="parsed",
            confidence_score=0.89,
            created_by_user_id="teacher_workflow",
        )

        # Verify workflow consistency
        assert class_event.user_id == student_event.created_by_user_id
        assert student_event.created_by_user_id == association_event.created_by_user_id
        assert student_event.student_id == association_event.student_id
        assert "class_workflow_2025" in student_event.class_ids

        # Verify all events can be serialized for event publishing
        for event in [class_event, student_event, association_event]:
            json_str = event.model_dump_json()
            assert isinstance(json_str, str)
            assert "teacher_workflow" in json_str

    def test_timestamp_consistency_across_events(self) -> None:
        """Test timestamp handling across all class management events."""
        class_event = ClassCreatedV1(
            class_id="class_time_test",
            class_designation="Time Test Class",
            course_codes=[CourseCode.ENG5],
            user_id="teacher_time",
        )
        student_event = StudentCreatedV1(
            student_id="student_time_test",
            first_name="Time",
            last_name="Test",
            student_email="time.test@example.com",
            class_ids=["class_time_test"],
            created_by_user_id="teacher_time",
        )
        association_event = EssayStudentAssociationUpdatedV1(
            batch_id="batch_time_test",
            essay_id="essay_time_test",
            student_id="student_time_test",
            first_name="Time",
            last_name="Test",
            student_email="time.test@example.com",
            association_method="manual",
            confidence_score=None,
            created_by_user_id="teacher_time",
        )

        # Test class event timestamp
        assert class_event.timestamp.tzinfo is not None
        assert class_event.timestamp.tzinfo == UTC
        now = datetime.now(UTC)
        time_diff = abs((now - class_event.timestamp).total_seconds())
        assert time_diff < 1.0  # Should be within 1 second

        # Test student event timestamp
        assert student_event.timestamp.tzinfo is not None
        assert student_event.timestamp.tzinfo == UTC
        time_diff = abs((now - student_event.timestamp).total_seconds())
        assert time_diff < 1.0  # Should be within 1 second

        # Test association event timestamp
        assert association_event.timestamp.tzinfo is not None
        assert association_event.timestamp.tzinfo == UTC
        time_diff = abs((now - association_event.timestamp).total_seconds())
        assert time_diff < 1.0  # Should be within 1 second
