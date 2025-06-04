"""Contract tests for Phase Outcome Event models.

Tests the Pydantic contracts between BOS and ELS services.
Following 070-testing-and-quality-assurance.mdc principles.
"""

from __future__ import annotations

from uuid import uuid4

from common_core.batch_service_models import BatchServiceCJAssessmentInitiateCommandDataV1
from common_core.enums import ProcessingEvent
from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.metadata_models import EntityReference, EssayProcessingInputRefV1


class TestELSBatchPhaseOutcomeContract:
    """Test ELSBatchPhaseOutcomeV1 contract compliance."""

    def test_outcome_event_serialization_roundtrip(self):
        """Test ELSBatchPhaseOutcomeV1 JSON serialization and deserialization."""
        batch_id = str(uuid4())
        correlation_id = uuid4()

        # Create valid processed essays
        processed_essays = [
            EssayProcessingInputRefV1(
                essay_id=str(uuid4()),
                text_storage_id=str(uuid4()),
            ),
        ]

        # Create outcome event
        original_event = ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name="spellcheck",
            phase_status="COMPLETED_SUCCESSFULLY",
            processed_essays=processed_essays,
            failed_essay_ids=["essay-2", "essay-3"],
            correlation_id=correlation_id,
        )

        # Test serialization
        json_data = original_event.model_dump_json()
        assert isinstance(json_data, str)
        assert batch_id in json_data
        assert "spellcheck" in json_data

        # Test deserialization
        deserialized_event = ELSBatchPhaseOutcomeV1.model_validate_json(json_data)

        # Verify all fields match
        assert deserialized_event.batch_id == original_event.batch_id
        assert deserialized_event.phase_name == original_event.phase_name
        assert deserialized_event.phase_status == original_event.phase_status
        assert deserialized_event.correlation_id == original_event.correlation_id
        assert len(deserialized_event.processed_essays) == len(original_event.processed_essays)
        assert len(deserialized_event.failed_essay_ids) == len(original_event.failed_essay_ids)


class TestBatchServiceCommandContracts:
    """Test batch service command model contracts."""

    def test_cj_assessment_command_serialization_roundtrip(self):
        """Test BatchServiceCJAssessmentInitiateCommandDataV1 JSON serialization
        and deserialization."""
        batch_id = str(uuid4())

        # Create valid essays
        essays = [
            EssayProcessingInputRefV1(
                essay_id=str(uuid4()),
                text_storage_id=str(uuid4()),
            ),
        ]

        # Create command
        original_command = BatchServiceCJAssessmentInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND,
            entity_ref=EntityReference(
                entity_id=batch_id,
                entity_type="batch",
            ),
            essays_to_process=essays,
            language="sv",
            course_code="SV101",
            class_designation="Class 9A",
            essay_instructions="Write about your summer vacation",
        )

        # Test serialization
        json_data = original_command.model_dump_json()
        assert isinstance(json_data, str)
        assert batch_id in json_data
        assert "SV101" in json_data

        # Test deserialization
        deserialized_command = (
            BatchServiceCJAssessmentInitiateCommandDataV1.model_validate_json(json_data)
        )

        # Verify all fields match
        assert deserialized_command.entity_ref.entity_id == original_command.entity_ref.entity_id
        assert deserialized_command.course_code == original_command.course_code
        assert deserialized_command.class_designation == original_command.class_designation
        assert deserialized_command.essay_instructions == original_command.essay_instructions
        assert len(deserialized_command.essays_to_process) == \
               len(original_command.essays_to_process)
