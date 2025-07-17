"""
ELS-BOS Communication Events

This module contains event models for communication between the Essay Lifecycle Service (ELS)
and the Batch Orchestrator Service (BOS) for dynamic pipeline orchestration.
"""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from ..metadata_models import EssayProcessingInputRefV1
from ..pipeline_models import PhaseName
from ..status_enums import BatchStatus


class ELSBatchPhaseOutcomeV1(BaseModel):
    """
    Event published by ELS to notify BOS about the completion of a processing phase for a batch.

    This event is critical for dynamic pipeline orchestration, allowing BOS to:
    1. Track phase completion across all essays in a batch
    2. Determine the next phase in the pipeline sequence
    3. Handle partial success scenarios (some essays succeed, others fail)
    4. Propagate only successful essays to the next phase

    The event includes the list of successfully processed essays with their updated
    text_storage_id references, which BOS uses to initiate the next phase.
    """

    batch_id: str = Field(
        ...,
        description="Unique identifier of the batch that completed the phase",
    )

    phase_name: PhaseName = Field(
        ...,
        description=(
            "Name of the phase that was completed. Must be a PhaseName enum value "
            "(e.g., PhaseName.SPELLCHECK, PhaseName.AI_FEEDBACK, PhaseName.CJ_ASSESSMENT)"
        ),
    )

    phase_status: BatchStatus = Field(
        ...,
        description=(
            "Overall status of the phase completion. Must be a BatchStatus enum value "
            "(e.g., BatchStatus.COMPLETED_SUCCESSFULLY, BatchStatus.COMPLETED_WITH_FAILURES, "
            "BatchStatus.FAILED_CRITICALLY)"
        ),
    )

    processed_essays: list[EssayProcessingInputRefV1] = Field(
        ...,
        description=(
            "List of essays that successfully completed this phase, with updated "
            "text_storage_id references for the next phase"
        ),
    )

    failed_essay_ids: list[str] = Field(
        ...,
        description=(
            "List of essay IDs that failed during this phase and should not be "
            "included in subsequent phases"
        ),
    )

    correlation_id: UUID = Field(
        default_factory=uuid4,
        description="Correlation ID for tracking related events across services",
    )

    @field_serializer("correlation_id")
    def serialize_uuid(self, uuid_val: UUID) -> str:
        """Serialize UUID to string."""
        return str(uuid_val)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "batch_id": "batch-123-456",
                "phase_name": "spellcheck",
                "phase_status": BatchStatus.COMPLETED_WITH_FAILURES.value,
                "processed_essays": [
                    {"essay_id": "essay-1", "text_storage_id": "storage-corrected-1"},
                    {"essay_id": "essay-2", "text_storage_id": "storage-corrected-2"},
                ],
                "failed_essay_ids": ["essay-3", "essay-4"],
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
            },
        }
    )
