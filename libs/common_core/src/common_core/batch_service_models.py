"""
Pydantic models for commands FROM Batch Orchestrator Service TO Essay Lifecycle Service.

This module defines the command data structures that
the Batch Orchestrator Service sends to ELS to initiate various processing phases.
"""

from __future__ import annotations

from .domain_enums import CourseCode
from .events.base_event_models import BaseEventData
from .metadata_models import EssayProcessingInputRefV1

__all__ = [
    "BatchServiceAIFeedbackInitiateCommandDataV1",
    "BatchServiceCJAssessmentInitiateCommandDataV1",
    "BatchServiceNLPInitiateCommandDataV1",
    "BatchServiceSpellcheckInitiateCommandDataV1",
    "BatchServiceStudentMatchingInitiateCommandDataV1",
]


class BatchServiceSpellcheckInitiateCommandDataV1(BaseEventData):
    """Command data for Batch Orchestrator Service to initiate spellcheck phase for a batch."""

    essays_to_process: list[EssayProcessingInputRefV1]
    language: str  # infered from course_code


class BatchServiceStudentMatchingInitiateCommandDataV1(BaseEventData):
    """Command data for Batch Orchestrator Service to initiate Phase 1 student matching."""

    essays_to_process: list[EssayProcessingInputRefV1]
    class_id: str  # Class ID for roster lookup


class BatchServiceNLPInitiateCommandDataV1(BaseEventData):
    """Command data for Batch Orchestrator Service to initiate NLP phase for a batch."""

    essays_to_process: list[EssayProcessingInputRefV1]
    language: str  # inferred from course_code


class BatchServiceAIFeedbackInitiateCommandDataV1(BaseEventData):
    """Command data for AI feedback with personalization context from Class Management Service."""

    essays_to_process: list[EssayProcessingInputRefV1]
    language: str  # inferred from course_code

    # Orchestration context (from BOS lean registration)
    course_code: CourseCode  # from batch registration
    essay_instructions: str  # from batch registration

    # Personalization context (from Class Management Service via enhanced BatchEssaysReady)
    class_type: str  # GUEST or REGULAR - determines AI feedback template selection
    teacher_first_name: str | None = None  # For personalized templates - REGULAR classes only
    teacher_last_name: str | None = None  # For personalized templates - REGULAR classes only


class BatchServiceCJAssessmentInitiateCommandDataV1(BaseEventData):
    """Command data for CJ assessment with educational context from Class Management Service."""

    essays_to_process: list[EssayProcessingInputRefV1]
    language: str  # inferred from course_code

    # Orchestration context (from BOS lean registration)
    course_code: CourseCode  # from batch registration
    essay_instructions: str  # from batch registration

    # Educational context (from Class Management Service via enhanced BatchEssaysReady)
    # Note: CJ assessment works identically for GUEST and REGULAR classes
    class_type: str  # GUEST or REGULAR - for audit/reporting purposes only
