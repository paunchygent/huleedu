"""
Pydantic models for commands FROM Batch Service TO Essay Lifecycle Service.

These models define the data structures for batch processing commands that
the Batch Service sends to ELS to initiate various processing phases.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .events.base_event_models import BaseEventData
from .metadata_models import EssayProcessingInputRefV1

__all__ = [
    "BatchServiceSpellcheckInitiateCommandDataV1",
    "BatchServiceNLPInitiateCommandDataV1",
    "BatchServiceAIFeedbackInitiateCommandDataV1",
    "BatchServiceCJAssessmentInitiateCommandDataV1",
]


class BatchServiceSpellcheckInitiateCommandDataV1(BaseEventData):
    """Command data for Batch Service to initiate spellcheck phase for a batch."""

    essays_to_process: List[EssayProcessingInputRefV1]
    language: str


class BatchServiceNLPInitiateCommandDataV1(BaseEventData):
    """Command data for Batch Service to initiate NLP phase for a batch."""

    essays_to_process: List[EssayProcessingInputRefV1]
    language: str


class BatchServiceAIFeedbackInitiateCommandDataV1(BaseEventData):
    """Command data for Batch Service to initiate AI feedback phase for a batch."""

    essays_to_process: List[EssayProcessingInputRefV1]
    course_code: str
    essay_instructions: str
    language: str
    teacher_name: Optional[str] = None
    class_designation: Optional[str] = None
    user_id_of_batch_owner: Optional[str] = None
    ai_specific_config: Optional[Dict[str, Any]] = None


class BatchServiceCJAssessmentInitiateCommandDataV1(BaseEventData):
    """Command data for Batch Service to initiate CJ assessment phase for a batch."""

    essays_for_cj: List[EssayProcessingInputRefV1]
    course_code: str
    essay_instructions: str
    language: Optional[str] = None
    user_id_of_batch_owner: Optional[str] = None
    cj_assessment_config: Optional[Dict[str, Any]] = None
