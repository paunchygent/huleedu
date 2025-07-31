"""
Unit tests for new event model contracts following HuleEdu Pydantic v2 standards.

Tests EventEnvelope serialization/deserialization, BatchValidationErrorsV1 model validation,
forward reference resolution, and Pydantic v2 compliance.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.error_enums import ErrorCode
from common_core.events.batch_coordination_events import (
    BatchErrorSummary,
    BatchEssaysReady,
    BatchValidationErrorsV1,
    EssayValidationError,
)
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import (
    EntityReference,
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import ProcessingStage
from pydantic import ValidationError

# Rebuild models to resolve forward references
EssayValidationError.model_rebuild()
BatchValidationErrorsV1.model_rebuild()


class TestEventContractsV2:
    """Test suite for v2 event contracts and Pydantic v2 compliance."""

    def test_event_envelope_serialization_roundtrip(self) -> None:
        """Test EventEnvelope serialization and deserialization for Kafka transport."""
        # Create test event data
        event_data = BatchEssaysReady(
            event="batch.essays.ready",
            batch_id="test-batch-123",
            ready_essays=[
                EssayProcessingInputRefV1(
                    essay_id="essay-1",
                    text_storage_id="storage-1",
                    student_name="John Doe",
                ),
                EssayProcessingInputRefV1(
                    essay_id="essay-2",
                    text_storage_id="storage-2",
                ),
            ],
            batch_entity=EntityReference(
                entity_id="test-batch-123",
                entity_type="batch",
            ),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id="test-batch-123", entity_type="batch"),
                timestamp=datetime.now(UTC),
                processing_stage=ProcessingStage.PROCESSING,
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Write about your favorite book",
            class_type="REGULAR",
            teacher_first_name="Jane",
            teacher_last_name="Smith",
        )

        # Create envelope
        envelope = EventEnvelope[BatchEssaysReady](
            event_type="huleedu.els.batch.essays.ready.v1",
            source_service="essay-lifecycle-service",
            correlation_id=uuid4(),
            data=event_data,
        )

        # Serialize to JSON bytes (as would be sent to Kafka)
        serialized = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")

        # Deserialize back
        deserialized_dict = json.loads(serialized.decode("utf-8"))
        reconstructed = EventEnvelope[BatchEssaysReady].model_validate(deserialized_dict)

        # Verify all fields match
        assert reconstructed.event_id == envelope.event_id
        assert reconstructed.event_type == envelope.event_type
        assert reconstructed.source_service == envelope.source_service
        assert reconstructed.correlation_id == envelope.correlation_id
        assert reconstructed.data.batch_id == event_data.batch_id
        assert len(reconstructed.data.ready_essays) == 2
        assert reconstructed.data.course_code == CourseCode.ENG5

    def test_batch_validation_errors_model_validation(self) -> None:
        """Test BatchValidationErrorsV1 model validation with structured errors."""
        # Create error detail
        error_detail = ErrorDetail(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Invalid file format",
            correlation_id=uuid4(),
            timestamp=datetime.now(UTC),
            service="file-service",
            operation="validate_file",
            details={"file_type": "invalid", "expected": "pdf"},
        )

        # Create validation error event
        validation_errors = BatchValidationErrorsV1(
            batch_id="test-batch-456",
            failed_essays=[
                EssayValidationError(
                    essay_id="essay-1",
                    file_name="essay1.txt",
                    error_detail=error_detail,
                )
            ],
            error_summary=BatchErrorSummary(
                total_errors=1,
                error_categories={"validation": 1},
                critical_failure=True,
            ),
            correlation_id=uuid4(),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id="test-batch-456", entity_type="batch"),
                timestamp=datetime.now(UTC),
                processing_stage=ProcessingStage.FAILED,
            ),
        )

        # Verify model structure
        assert validation_errors.batch_id == "test-batch-456"
        assert len(validation_errors.failed_essays) == 1
        assert validation_errors.error_summary.critical_failure is True
        assert validation_errors.error_summary.total_errors == 1
        assert (
            validation_errors.failed_essays[0].error_detail.error_code == ErrorCode.VALIDATION_ERROR
        )

    def test_forward_reference_resolution(self) -> None:
        """Test that forward references (ErrorDetail) are properly resolved."""
        # This test verifies that the TYPE_CHECKING import pattern works correctly
        # Create an EssayValidationError with ErrorDetail
        error_detail = ErrorDetail(
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            message="File not found",
            correlation_id=uuid4(),
            timestamp=datetime.now(UTC),
            service="file-service",
            operation="fetch_content",
            details={"file_id": "missing-file"},
        )

        validation_error = EssayValidationError(
            essay_id="essay-missing",
            file_name="missing.pdf",
            error_detail=error_detail,
        )

        # Serialize and deserialize to ensure forward ref works
        serialized = validation_error.model_dump(mode="json")
        reconstructed = EssayValidationError.model_validate(serialized)

        assert reconstructed.error_detail.error_code == ErrorCode.RESOURCE_NOT_FOUND
        assert reconstructed.error_detail.service == "file-service"

    def test_event_envelope_with_validation_errors(self) -> None:
        """Test EventEnvelope wrapping BatchValidationErrorsV1 for Kafka transport."""
        # Create comprehensive validation error event
        error_events = []
        for i in range(3):
            error_detail = ErrorDetail(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=f"Validation failed for essay {i + 1}",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="file-service",
                operation="validate",
                details={"reason": f"reason_{i + 1}"},
            )

            error_events.append(
                EssayValidationError(
                    essay_id=f"essay-{i + 1}",
                    file_name=f"essay{i + 1}.pdf",
                    error_detail=error_detail,
                )
            )

        validation_event = BatchValidationErrorsV1(
            batch_id="test-batch-errors",
            failed_essays=error_events,
            error_summary=BatchErrorSummary(
                total_errors=3,
                error_categories={"validation": 3},
                critical_failure=False,  # Partial failure
            ),
            correlation_id=uuid4(),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id="test-batch-errors", entity_type="batch"),
                timestamp=datetime.now(UTC),
                processing_stage=ProcessingStage.PROCESSING,
            ),
        )

        # Wrap in envelope
        envelope = EventEnvelope[BatchValidationErrorsV1](
            event_type="huleedu.els.batch.validation.errors.v1",
            source_service="essay-lifecycle-service",
            correlation_id=validation_event.correlation_id,
            data=validation_event,
            metadata={"trace_id": "test-trace-123"},
        )

        # Test serialization for Kafka
        kafka_payload = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        assert isinstance(kafka_payload, bytes)

        # Verify deserialization preserves all data
        deserialized = json.loads(kafka_payload.decode("utf-8"))
        reconstructed = EventEnvelope[BatchValidationErrorsV1].model_validate(deserialized)

        assert len(reconstructed.data.failed_essays) == 3
        assert reconstructed.data.error_summary.critical_failure is False
        assert reconstructed.metadata == {"trace_id": "test-trace-123"}

    def test_pydantic_v2_mode_json_compliance(self) -> None:
        """Test Pydantic v2 mode='json' serialization compliance."""
        # Test that enums are properly serialized using mode='json'
        event_data = BatchEssaysReady(
            batch_id="test-pydantic-v2",
            ready_essays=[],
            batch_entity=EntityReference(entity_id="test-pydantic-v2", entity_type="batch"),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id="test-pydantic-v2", entity_type="batch"),
                timestamp=datetime.now(UTC),
                processing_stage=ProcessingStage.INITIALIZED,  # Enum field
            ),
            course_code=CourseCode.ENG5,  # Enum field
            course_language="en",
            essay_instructions="Test instructions",
            class_type="GUEST",
        )

        # Serialize with mode='json' (Pydantic v2 pattern)
        serialized = event_data.model_dump(mode="json")

        # Verify enums are serialized to their values
        assert (
            serialized["metadata"]["processing_stage"] == "initialized"
        )  # Enum value is lowercase
        assert serialized["course_code"] == "ENG5"

        # Verify reconstruction works
        reconstructed = BatchEssaysReady.model_validate(serialized)
        assert reconstructed.metadata.processing_stage == ProcessingStage.INITIALIZED
        assert reconstructed.course_code == CourseCode.ENG5

    def test_model_validation_errors(self) -> None:
        """Test that models properly validate required fields and types."""
        # Test missing required field
        with pytest.raises(ValidationError) as exc_info:
            BatchValidationErrorsV1(
                # Missing batch_id
                failed_essays=[],
                error_summary=BatchErrorSummary(
                    total_errors=0,
                    error_categories={},
                ),
                correlation_id=uuid4(),
            )

        assert "batch_id" in str(exc_info.value)

        # Test invalid type
        with pytest.raises(ValidationError) as exc_info:
            BatchErrorSummary(
                total_errors="not-a-number",  # Should be int
                error_categories={},
            )

        assert "total_errors" in str(exc_info.value)

    def test_essay_validation_error_timestamp(self) -> None:
        """Test that EssayValidationError properly sets failed_at timestamp."""
        error_detail = ErrorDetail(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Test error",
            correlation_id=uuid4(),
            timestamp=datetime.now(UTC),
            service="test-service",
            operation="test-operation",
        )

        # Create without explicit failed_at
        validation_error = EssayValidationError(
            essay_id="test-essay",
            file_name="test.pdf",
            error_detail=error_detail,
        )

        # Verify failed_at was auto-populated
        assert validation_error.failed_at is not None
        assert isinstance(validation_error.failed_at, datetime)
        assert validation_error.failed_at.tzinfo is not None

    def test_batch_error_summary_categories(self) -> None:
        """Test BatchErrorSummary properly tracks error categories."""
        # Create summary with multiple error categories
        summary = BatchErrorSummary(
            total_errors=10,
            error_categories={
                "validation": 5,
                "extraction": 3,
                "system": 2,
            },
            critical_failure=False,
        )

        # Verify category tracking
        assert summary.total_errors == 10
        assert len(summary.error_categories) == 3
        assert summary.error_categories["validation"] == 5
        assert summary.critical_failure is False

        # Test critical failure scenario
        critical_summary = BatchErrorSummary(
            total_errors=5,
            error_categories={"critical": 5},
            critical_failure=True,
        )

        assert critical_summary.critical_failure is True
