"""
Pydantic models for requests FROM Essay Lifecycle Service TO Specialized Services.

These models define the data structures for individual essay processing requests
that ELS dispatches to specialized services based on batch commands.
"""

from __future__ import annotations

from .events.ai_feedback_events import AIFeedbackInputDataV1
from .events.base_event_models import EnhancedProcessingUpdate

__all__ = [
    "EssayLifecycleSpellcheckRequestV1",
    "EssayLifecycleNLPRequestV1",
    "EssayLifecycleAIFeedbackRequestV1",
]


class EssayLifecycleSpellcheckRequestV1(EnhancedProcessingUpdate):
    """Request data for ELS to request spellcheck processing for an individual essay."""

    text_storage_id: str
    language: str


class EssayLifecycleNLPRequestV1(EnhancedProcessingUpdate):
    """Request data for ELS to request NLP processing for an individual essay."""

    text_storage_id: str
    language: str


class EssayLifecycleAIFeedbackRequestV1(EnhancedProcessingUpdate):
    """Request data for ELS to request AI feedback processing for an individual essay."""

    processing_input: AIFeedbackInputDataV1
