"""
Unit tests for validation event models.

Tests the event models used for NLP Service Phase 1 student matching integration,
including student association confirmations and validation timeout processing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from common_core.event_enums import ProcessingEvent
from common_core.events.validation_events import (
    StudentAssociation,
    StudentAssociationConfirmation,
    StudentAssociationsConfirmedV1,
    ValidationTimeoutProcessedV1,
)


class TestStudentAssociationConfirmation:
    """Test suite for StudentAssociationConfirmation model."""

    def test_model_creation_with_human_validation(self) -> None:
        """Test creating StudentAssociationConfirmation with human validation."""
        validated_at = datetime.now(UTC)

        model = StudentAssociationConfirmation(
            essay_id="essay_123",
            student_id="student_456",
            confidence_score=0.95,
            validation_method="human",
            validated_by="teacher_789",
            validated_at=validated_at,
        )

        assert model.essay_id == "essay_123"
        assert model.student_id == "student_456"
        assert model.confidence_score == 0.95
        assert model.validation_method == "human"
        assert model.validated_by == "teacher_789"
        assert model.validated_at == validated_at

    def test_model_creation_with_timeout_validation(self) -> None:
        """Test creating StudentAssociationConfirmation with timeout validation."""
        model = StudentAssociationConfirmation(
            essay_id="essay_timeout",
            student_id="student_timeout",
            confidence_score=0.85,
            validation_method="timeout",
            validated_by=None,  # No human validator for timeout
        )

        assert model.essay_id == "essay_timeout"
        assert model.student_id == "student_timeout"
        assert model.confidence_score == 0.85
        assert model.validation_method == "timeout"
        assert model.validated_by is None
        assert isinstance(model.validated_at, datetime)

    def test_model_creation_with_auto_validation(self) -> None:
        """Test creating StudentAssociationConfirmation with auto validation."""
        model = StudentAssociationConfirmation(
            essay_id="essay_auto",
            student_id="student_auto",
            confidence_score=0.98,
            validation_method="auto",
            validated_by=None,
        )

        assert model.validation_method == "auto"
        assert model.validated_by is None
        assert model.confidence_score == 0.98

    def test_model_creation_with_no_match(self) -> None:
        """Test creating StudentAssociationConfirmation with no student match."""
        model = StudentAssociationConfirmation(
            essay_id="essay_no_match",
            student_id=None,  # No match found
            confidence_score=0.0,
            validation_method="human",
            validated_by="teacher_reviewer",
        )

        assert model.essay_id == "essay_no_match"
        assert model.student_id is None
        assert model.confidence_score == 0.0
        assert model.validation_method == "human"
        assert model.validated_by == "teacher_reviewer"

    def test_model_serialization_deserialization(self) -> None:
        """Test that student association confirmation can be serialized and deserialized."""
        validated_at = datetime.now(UTC)
        original_confirmation = StudentAssociationConfirmation(
            essay_id="essay_serialize",
            student_id="student_serialize",
            confidence_score=0.92,
            validation_method="human",
            validated_by="teacher_serialize",
            validated_at=validated_at,
        )

        # Serialize to JSON
        json_data = original_confirmation.model_dump_json()
        assert isinstance(json_data, str)

        # Deserialize back to model
        data_dict = json.loads(json_data)
        reconstructed_confirmation = StudentAssociationConfirmation.model_validate(data_dict)

        # Verify all fields match
        assert reconstructed_confirmation.essay_id == original_confirmation.essay_id
        assert reconstructed_confirmation.student_id == original_confirmation.student_id
        assert reconstructed_confirmation.confidence_score == original_confirmation.confidence_score
        assert (
            reconstructed_confirmation.validation_method == original_confirmation.validation_method
        )
        assert reconstructed_confirmation.validated_by == original_confirmation.validated_by
        assert reconstructed_confirmation.validated_at == original_confirmation.validated_at

    def test_validation_method_literal_constraint(self) -> None:
        """Test that validation_method only accepts specific literal values."""
        # Test valid values
        for method in ["human", "timeout", "auto"]:
            model = StudentAssociationConfirmation(
                essay_id="essay_test",
                student_id="student_test",
                confidence_score=0.5,
                validation_method=method,  # type: ignore[arg-type]
                validated_by=None,
            )
            assert model.validation_method == method

    def test_confidence_score_ranges(self) -> None:
        """Test various confidence score values."""
        # Perfect match
        perfect_model = StudentAssociationConfirmation(
            essay_id="essay_perfect",
            student_id="student_perfect",
            confidence_score=1.0,
            validation_method="auto",
            validated_by=None,
        )
        assert perfect_model.confidence_score == 1.0

        # No confidence
        no_conf_model = StudentAssociationConfirmation(
            essay_id="essay_no_conf",
            student_id=None,
            confidence_score=0.0,
            validation_method="human",
            validated_by="teacher_review",
        )
        assert no_conf_model.confidence_score == 0.0

        # Mid-range confidence
        mid_model = StudentAssociationConfirmation(
            essay_id="essay_mid",
            student_id="student_mid",
            confidence_score=0.75,
            validation_method="timeout",
            validated_by=None,
        )
        assert mid_model.confidence_score == 0.75


class TestStudentAssociationsConfirmedV1:
    """Test suite for StudentAssociationsConfirmedV1 event model."""

    def test_model_creation_with_human_validations(self) -> None:
        """Test creating StudentAssociationsConfirmedV1 with human validations."""
        associations = [
            StudentAssociationConfirmation(
                essay_id="essay_1",
                student_id="student_1",
                confidence_score=0.95,
                validation_method="human",
                validated_by="teacher_123",
            ),
            StudentAssociationConfirmation(
                essay_id="essay_2",
                student_id="student_2",
                confidence_score=0.88,
                validation_method="human",
                validated_by="teacher_123",
            ),
        ]

        model = StudentAssociationsConfirmedV1(
            batch_id="batch_human",
            class_id="class_human",
            associations=associations,
            timeout_triggered=False,
            validation_summary={"human": 2, "timeout": 0, "auto": 0},
        )

        assert model.event_name == ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED
        assert model.batch_id == "batch_human"
        assert model.class_id == "class_human"
        assert len(model.associations) == 2
        assert model.timeout_triggered is False
        assert model.validation_summary == {"human": 2, "timeout": 0, "auto": 0}

    def test_model_creation_with_timeout_triggered(self) -> None:
        """Test creating StudentAssociationsConfirmedV1 with timeout triggered."""
        associations = [
            StudentAssociationConfirmation(
                essay_id="essay_timeout_1",
                student_id="student_timeout_1",
                confidence_score=0.85,
                validation_method="timeout",
                validated_by=None,
            ),
            StudentAssociationConfirmation(
                essay_id="essay_timeout_2",
                student_id=None,  # No match
                confidence_score=0.0,
                validation_method="timeout",
                validated_by=None,
            ),
        ]

        model = StudentAssociationsConfirmedV1(
            batch_id="batch_timeout",
            class_id="class_timeout",
            associations=associations,
            timeout_triggered=True,
            validation_summary={"human": 0, "timeout": 2, "auto": 0},
        )

        assert model.batch_id == "batch_timeout"
        assert model.timeout_triggered is True
        assert model.validation_summary["timeout"] == 2

    def test_model_creation_with_mixed_validations(self) -> None:
        """Test creating StudentAssociationsConfirmedV1 with mixed validation methods."""
        associations = [
            StudentAssociationConfirmation(
                essay_id="essay_mix_1",
                student_id="student_mix_1",
                confidence_score=0.95,
                validation_method="human",
                validated_by="teacher_mix",
            ),
            StudentAssociationConfirmation(
                essay_id="essay_mix_2",
                student_id="student_mix_2",
                confidence_score=0.88,
                validation_method="timeout",
                validated_by=None,
            ),
            StudentAssociationConfirmation(
                essay_id="essay_mix_3",
                student_id="student_mix_3",
                confidence_score=0.99,
                validation_method="auto",
                validated_by=None,
            ),
            StudentAssociationConfirmation(
                essay_id="essay_mix_4",
                student_id=None,  # No match
                confidence_score=0.0,
                validation_method="human",
                validated_by="teacher_mix",
            ),
        ]

        model = StudentAssociationsConfirmedV1(
            batch_id="batch_mixed",
            class_id="class_mixed",
            associations=associations,
            timeout_triggered=False,
            validation_summary={"human": 2, "timeout": 1, "auto": 1},
        )

        assert len(model.associations) == 4
        assert model.validation_summary["human"] == 2
        assert model.validation_summary["timeout"] == 1
        assert model.validation_summary["auto"] == 1

    def test_model_serialization_deserialization(self) -> None:
        """Test that student associations confirmed event can be serialized and deserialized."""
        associations = [
            StudentAssociationConfirmation(
                essay_id="essay_serialize_1",
                student_id="student_serialize_1",
                confidence_score=0.92,
                validation_method="human",
                validated_by="teacher_serialize",
            ),
        ]

        original_event = StudentAssociationsConfirmedV1(
            batch_id="batch_serialize",
            class_id="class_serialize",
            associations=associations,
            timeout_triggered=False,
            validation_summary={"human": 1, "timeout": 0, "auto": 0},
        )

        # Serialize to JSON
        json_data = original_event.model_dump_json()
        assert isinstance(json_data, str)

        # Deserialize back to model
        data_dict = json.loads(json_data)
        reconstructed_event = StudentAssociationsConfirmedV1.model_validate(data_dict)

        # Verify all fields match
        assert reconstructed_event.event_name == original_event.event_name
        assert reconstructed_event.batch_id == original_event.batch_id
        assert reconstructed_event.class_id == original_event.class_id
        assert len(reconstructed_event.associations) == len(original_event.associations)
        assert reconstructed_event.timeout_triggered == original_event.timeout_triggered
        assert reconstructed_event.validation_summary == original_event.validation_summary

        # Verify association details
        orig_assoc = original_event.associations[0]
        recon_assoc = reconstructed_event.associations[0]
        assert recon_assoc.essay_id == orig_assoc.essay_id
        assert recon_assoc.student_id == orig_assoc.student_id
        assert recon_assoc.confidence_score == orig_assoc.confidence_score
        assert recon_assoc.validation_method == orig_assoc.validation_method

    def test_event_name_default(self) -> None:
        """Test that event_name defaults to correct ProcessingEvent."""
        model = StudentAssociationsConfirmedV1(
            batch_id="batch_default",
            class_id="class_default",
            associations=[],
            validation_summary={"human": 0, "timeout": 0, "auto": 0},
        )

        assert model.event_name == ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED

    def test_empty_associations_list(self) -> None:
        """Test creating event with empty associations list."""
        model = StudentAssociationsConfirmedV1(
            batch_id="batch_empty",
            class_id="class_empty",
            associations=[],
            timeout_triggered=True,
            validation_summary={"human": 0, "timeout": 0, "auto": 0},
        )

        assert len(model.associations) == 0
        assert model.timeout_triggered is True


class TestStudentAssociation:
    """Test suite for legacy StudentAssociation model."""

    def test_legacy_model_backward_compatibility(self) -> None:
        """Test legacy StudentAssociation model for backward compatibility."""
        model = StudentAssociation(
            essay_id="essay_legacy",
            student_first_name="Anna",
            student_last_name="Svensson",
            student_email="anna.svensson@school.se",
            confidence_score=0.87,
            is_confirmed=True,
        )

        assert model.essay_id == "essay_legacy"
        assert model.student_first_name == "Anna"
        assert model.student_last_name == "Svensson"
        assert model.student_email == "anna.svensson@school.se"
        assert model.confidence_score == 0.87
        assert model.is_confirmed is True

    def test_legacy_model_without_email(self) -> None:
        """Test legacy StudentAssociation model without email."""
        model = StudentAssociation(
            essay_id="essay_no_email",
            student_first_name="Erik",
            student_last_name="Johansson",
            student_email=None,
            confidence_score=0.65,
            is_confirmed=False,
        )

        assert model.student_email is None
        assert model.is_confirmed is False


class TestValidationTimeoutProcessedV1:
    """Test suite for ValidationTimeoutProcessedV1 event model."""

    def test_timeout_event_creation(self) -> None:
        """Test creating ValidationTimeoutProcessedV1 event."""
        auto_confirmed = [
            StudentAssociation(
                essay_id="essay_auto_1",
                student_first_name="Auto",
                student_last_name="Confirmed",
                student_email="auto.confirmed@school.se",
                confidence_score=0.85,
                is_confirmed=True,
            ),
        ]

        model = ValidationTimeoutProcessedV1(
            batch_id="batch_timeout_processed",
            user_id="teacher_timeout",
            timeout_hours=24,
            auto_confirmed_associations=auto_confirmed,
            guest_essays=["essay_guest_1", "essay_guest_2"],
            guest_class_created=True,
            guest_class_id="guest_class_auto_created",
        )

        assert model.batch_id == "batch_timeout_processed"
        assert model.user_id == "teacher_timeout"
        assert model.timeout_hours == 24
        assert len(model.auto_confirmed_associations) == 1
        assert len(model.guest_essays) == 2
        assert model.guest_class_created is True
        assert model.guest_class_id == "guest_class_auto_created"


class TestRealWorldWorkflowScenarios:
    """Test realistic NLP Phase 1 student matching workflow scenarios."""

    def test_regular_batch_workflow_scenario(self) -> None:
        """Test complete REGULAR batch workflow with human validation."""
        # Scenario: Teacher uploads batch to class, NLP suggests matches, teacher validates
        associations = [
            StudentAssociationConfirmation(
                essay_id="essay_anna_narrative",
                student_id="student_anna_123",
                confidence_score=0.95,
                validation_method="human",
                validated_by="teacher_workflow",
            ),
            StudentAssociationConfirmation(
                essay_id="essay_erik_report",
                student_id="student_erik_456",
                confidence_score=0.88,
                validation_method="human",
                validated_by="teacher_workflow",
            ),
            StudentAssociationConfirmation(
                essay_id="essay_unknown",
                student_id=None,  # Teacher couldn't identify
                confidence_score=0.0,
                validation_method="human",
                validated_by="teacher_workflow",
            ),
        ]

        confirmed_event = StudentAssociationsConfirmedV1(
            batch_id="batch_9a_english_spring_2025",
            class_id="class_9a_english",
            associations=associations,
            timeout_triggered=False,
            validation_summary={"human": 3, "timeout": 0, "auto": 0},
        )

        # Verify workflow consistency
        assert confirmed_event.event_name == ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED
        assert confirmed_event.batch_id == "batch_9a_english_spring_2025"
        assert confirmed_event.class_id == "class_9a_english"
        assert len(confirmed_event.associations) == 3
        assert confirmed_event.timeout_triggered is False

        # Verify human validation
        human_validated = [a for a in associations if a.validation_method == "human"]
        assert len(human_validated) == 3
        assert all(a.validated_by == "teacher_workflow" for a in human_validated)

        # Verify mixed outcomes (matched and unmatched)
        matched = [a for a in associations if a.student_id is not None]
        unmatched = [a for a in associations if a.student_id is None]
        assert len(matched) == 2
        assert len(unmatched) == 1

    def test_timeout_workflow_scenario(self) -> None:
        """Test REGULAR batch workflow with timeout triggering auto-confirmation."""
        # Scenario: Teacher doesn't validate within 24 hours, system auto-confirms best matches
        associations = [
            StudentAssociationConfirmation(
                essay_id="essay_timeout_1",
                student_id="student_high_conf",
                confidence_score=0.92,  # High confidence - auto-confirmed
                validation_method="timeout",
                validated_by=None,
            ),
            StudentAssociationConfirmation(
                essay_id="essay_timeout_2",
                student_id=None,  # Low confidence - treated as no match
                confidence_score=0.45,
                validation_method="timeout",
                validated_by=None,
            ),
        ]

        timeout_event = StudentAssociationsConfirmedV1(
            batch_id="batch_timeout_scenario",
            class_id="class_timeout",
            associations=associations,
            timeout_triggered=True,
            validation_summary={"human": 0, "timeout": 2, "auto": 0},
        )

        # Verify timeout behavior
        assert timeout_event.timeout_triggered is True
        assert timeout_event.validation_summary["timeout"] == 2
        assert all(a.validated_by is None for a in associations)
        assert all(a.validation_method == "timeout" for a in associations)

    def test_guest_batch_workflow_scenario(self) -> None:
        """Test GUEST batch workflow (bypasses student matching entirely)."""
        # GUEST batches should not generate StudentAssociationsConfirmedV1 events
        # This test verifies the model supports the case where it might be used
        # in error handling or logging scenarios for GUEST batches

        # Empty associations for GUEST batch (should not happen in normal flow)
        guest_event = StudentAssociationsConfirmedV1(
            batch_id="batch_guest_error_case",
            class_id="guest_class_auto",
            associations=[],
            timeout_triggered=False,
            validation_summary={"human": 0, "timeout": 0, "auto": 0},
        )

        assert len(guest_event.associations) == 0
        assert guest_event.batch_id == "batch_guest_error_case"

    def test_serialization_for_kafka_publishing(self) -> None:
        """Test that all validation events can be serialized for Kafka publishing."""
        associations = [
            StudentAssociationConfirmation(
                essay_id="essay_kafka_test",
                student_id="student_kafka_test",
                confidence_score=0.89,
                validation_method="human",
                validated_by="teacher_kafka",
            ),
        ]

        event = StudentAssociationsConfirmedV1(
            batch_id="batch_kafka_test",
            class_id="class_kafka_test",
            associations=associations,
            timeout_triggered=False,
            validation_summary={"human": 1, "timeout": 0, "auto": 0},
        )

        # Serialize for Kafka (following Rule 051 patterns)
        json_str = event.model_dump_json()
        assert isinstance(json_str, str)

        # Verify key fields are present in JSON
        assert "student.associations.confirmed" in json_str
        assert "batch_kafka_test" in json_str
        assert "class_kafka_test" in json_str
        assert "essay_kafka_test" in json_str
        assert "teacher_kafka" in json_str

        # Verify it can be deserialized
        data_dict = json.loads(json_str)
        reconstructed = StudentAssociationsConfirmedV1.model_validate(data_dict)
        assert reconstructed.batch_id == event.batch_id
