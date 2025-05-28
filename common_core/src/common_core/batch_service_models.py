"""
Pydantic models for commands FROM Batch Orchestrator Service TO Essay Lifecycle Service.

This module defines the command data structures that
the Batch Orchestrator Service sends to ELS to initiate various processing phases.
"""

from __future__ import annotations

from typing import List

from .events.base_event_models import BaseEventData
from .metadata_models import EssayProcessingInputRefV1

__all__ = [
    "BatchServiceSpellcheckInitiateCommandDataV1",
    "BatchServiceNLPInitiateCommandDataV1",
    "BatchServiceAIFeedbackInitiateCommandDataV1",
    "BatchServiceCJAssessmentInitiateCommandDataV1",
]


class BatchServiceSpellcheckInitiateCommandDataV1(BaseEventData):
    """Command data for Batch Orchestrator Service to initiate spellcheck phase for a batch."""

    essays_to_process: List[EssayProcessingInputRefV1]
    language: str


class BatchServiceNLPInitiateCommandDataV1(BaseEventData):
    """Command data for Batch Orchestrator Service to initiate NLP phase for a batch."""

    essays_to_process: List[EssayProcessingInputRefV1]
    language: str


class BatchServiceAIFeedbackInitiateCommandDataV1(BaseEventData):
    """Command data for Batch Orchestrator Service to initiate AI feedback phase for a batch."""

    essays_to_process: List[EssayProcessingInputRefV1]
    language: str
    # AI feedback specific fields
    course_code: str
    teacher_name: str
    class_designation: str
    essay_instructions: str


class BatchServiceCJAssessmentInitiateCommandDataV1(BaseEventData):
    """Command data for Batch Orchestrator Service to initiate CJ assessment phase for a batch."""

    essays_for_cj: List[EssayProcessingInputRefV1]
    language: str
    # CJ assessment specific context
    course_code: str
    teacher_name: str
    class_designation: str
    essay_instructions: str
