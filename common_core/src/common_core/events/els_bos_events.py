"""
ELS-BOS Communication Events

This module contains event models for communication between the Essay Lifecycle Service (ELS)
and the Batch Orchestrator Service (BOS) for dynamic pipeline orchestration.
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from ..metadata_models import EssayProcessingInputRefV1


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
        description="Unique identifier of the batch that completed the phase"
    )

    phase_name: str = Field(
        ...,
        description="Name of the phase that was completed (e.g., 'spellcheck', 'ai_feedback', 'cj_assessment')"
    )

    phase_status: str = Field(
        ...,
        description="Overall status of the phase completion (e.g., 'COMPLETED_SUCCESSFULLY', 'COMPLETED_WITH_FAILURES', 'FAILED_CRITICALLY')"
    )

    processed_essays: List[EssayProcessingInputRefV1] = Field(
        ...,
        description="List of essays that successfully completed this phase, with updated text_storage_id references for the next phase"
    )

    failed_essay_ids: List[str] = Field(
        ...,
        description="List of essay IDs that failed during this phase and should not be included in subsequent phases"
    )

    correlation_id: Optional[UUID] = Field(
        None,
        description="Optional correlation ID for tracking related events across services"
    )

    class Config:
        """Pydantic configuration for the event model."""
        json_encoders = {
            UUID: str
        }
        json_schema_extra = {
            "example": {
                "batch_id": "batch-123-456",
                "phase_name": "spellcheck",
                "phase_status": "COMPLETED_WITH_FAILURES",
                "processed_essays": [
                    {
                        "essay_id": "essay-1",
                        "text_storage_id": "storage-corrected-1"
                    },
                    {
                        "essay_id": "essay-2",
                        "text_storage_id": "storage-corrected-2"
                    }
                ],
                "failed_essay_ids": ["essay-3", "essay-4"],
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
