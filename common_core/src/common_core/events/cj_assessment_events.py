"""CJ Assessment service event models.

This module defines event contracts for communication between services
regarding Comparative Judgment (CJ) assessment processing.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import Field

from ..enums import ProcessingEvent
from ..metadata_models import EssayProcessingInputRefV1, SystemProcessingMetadata
from .base_event_models import BaseEventData, ProcessingUpdate

__all__ = [
    "ELS_CJAssessmentRequestV1",
    "CJAssessmentCompletedV1",
    "CJAssessmentFailedV1",
]


class ELS_CJAssessmentRequestV1(BaseEventData):
    """Request event from ELS to CJ Assessment Service to perform CJ on a list of essays."""

    event_name: ProcessingEvent = Field(default=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)
    system_metadata: SystemProcessingMetadata  # Populated by ELS
    essays_for_cj: List[EssayProcessingInputRefV1]
    language: str
    course_code: str
    essay_instructions: str
    # class_designation: str  # Deferred (YAGNI)


class CJAssessmentCompletedV1(ProcessingUpdate):
    """Result event from CJ Assessment Service to ELS reporting successful completion."""

    event_name: ProcessingEvent = Field(default=ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
    # entity_ref (from BaseEventData) is the BOS Batch ID this result pertains to
    # status (from ProcessingUpdate) indicates outcome (e.g. COMPLETED_SUCCESSFULLY)
    # system_metadata (from ProcessingUpdate) populated by CJ Assessment Service

    cj_assessment_job_id: str  # The internal ID from CJ_BatchUpload, for detailed log/result lookup
    rankings: List[Dict[str, Any]]  # The consumer-friendly ranking data
    # Example: [{"els_essay_id": "uuid1", "rank": 1, "score": 0.75}, ...]


class CJAssessmentFailedV1(ProcessingUpdate):
    """Failure event from CJ Assessment Service to ELS reporting processing failure."""

    event_name: ProcessingEvent = Field(default=ProcessingEvent.CJ_ASSESSMENT_FAILED)
    # entity_ref (from BaseEventData) is the BOS Batch ID
    # status (from ProcessingUpdate) indicates failure
    # system_metadata (from ProcessingUpdate) should contain detailed error_info

    cj_assessment_job_id: str  # Internal CJ Job ID for traceability
