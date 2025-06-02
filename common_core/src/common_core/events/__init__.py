"""
Event models for HuleEdu microservices.
"""

from .base_event_models import BaseEventData, EventTracker, ProcessingUpdate
from .cj_assessment_events import (
    CJAssessmentCompletedV1,
    CJAssessmentFailedV1,
    ELS_CJAssessmentRequestV1,
)
from .envelope import EventEnvelope
from .spellcheck_models import SpellcheckRequestedDataV1, SpellcheckResultDataV1

__all__ = [
    "EventEnvelope",
    "BaseEventData",
    "ProcessingUpdate",
    "EventTracker",
    "SpellcheckRequestedDataV1",
    "SpellcheckResultDataV1",
    "ELS_CJAssessmentRequestV1",
    "CJAssessmentCompletedV1",
    "CJAssessmentFailedV1",
]
