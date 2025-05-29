"""
HuleEdu Common Core Package.
"""

# Required for Pydantic model rebuilding - Union is used in forward references
# in base_event_models.py and must be available when model_rebuild() is called
from typing import Union

from .batch_service_models import (
    BatchServiceAIFeedbackInitiateCommandDataV1,
    BatchServiceCJAssessmentInitiateCommandDataV1,
    BatchServiceNLPInitiateCommandDataV1,
    BatchServiceSpellcheckInitiateCommandDataV1,
)
from .enums import (
    BatchStatus,
    ContentType,
    ErrorCode,
    EssayStatus,
    ProcessingEvent,
    ProcessingStage,
    topic_name,
)
from .essay_service_models import (
    EssayLifecycleAIFeedbackRequestV1,
    EssayLifecycleNLPRequestV1,
    EssayLifecycleSpellcheckRequestV1,
)
from .events.ai_feedback_events import AIFeedbackInputDataV1
from .events.base_event_models import (
    BaseEventData,
    EventTracker,
    ProcessingUpdate,
)
from .events.envelope import EventEnvelope
from .events.spellcheck_models import SpellcheckRequestedDataV1, SpellcheckResultDataV1
from .metadata_models import (
    CancellationMetadata,
    EntityReference,
    EssayProcessingInputRefV1,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
    UserActivityMetadata,
)
from .pipeline_models import (
    EssayProcessingCounts,
    PipelineExecutionStatus,
    PipelineStateDetail,
    ProcessingPipelineState,
)

__all__ = [
    # Enums
    "ProcessingStage",
    "ProcessingEvent",
    "EssayStatus",
    "BatchStatus",
    "ContentType",
    "ErrorCode",
    "topic_name",
    # Metadata Models
    "EntityReference",
    "SystemProcessingMetadata",
    "StorageReferenceMetadata",
    "UserActivityMetadata",
    "CancellationMetadata",
    "EssayProcessingInputRefV1",
    # Pipeline Models
    "PipelineExecutionStatus",
    "EssayProcessingCounts",
    "PipelineStateDetail",
    "ProcessingPipelineState",
    # Event Infrastructure
    "EventEnvelope",
    "BaseEventData",
    "ProcessingUpdate",
    "EventTracker",
    # Specific Event Data Models
    "SpellcheckRequestedDataV1",
    "SpellcheckResultDataV1",
    "AIFeedbackInputDataV1",
    # Batch Service Command Models
    "BatchServiceSpellcheckInitiateCommandDataV1",
    "BatchServiceNLPInitiateCommandDataV1",
    "BatchServiceAIFeedbackInitiateCommandDataV1",
    "BatchServiceCJAssessmentInitiateCommandDataV1",
    # Essay Service Request Models
    "EssayLifecycleSpellcheckRequestV1",
    "EssayLifecycleNLPRequestV1",
    "EssayLifecycleAIFeedbackRequestV1",
]

# Rebuild models to resolve forward references after all imports
# Now that all enums are imported above, forward references should resolve successfully
BaseEventData.model_rebuild(raise_errors=True)
ProcessingUpdate.model_rebuild(raise_errors=True)
EventTracker.model_rebuild(raise_errors=True)
SpellcheckRequestedDataV1.model_rebuild(raise_errors=True)
SpellcheckResultDataV1.model_rebuild(raise_errors=True)
AIFeedbackInputDataV1.model_rebuild(raise_errors=True)
BatchServiceSpellcheckInitiateCommandDataV1.model_rebuild(raise_errors=True)
BatchServiceNLPInitiateCommandDataV1.model_rebuild(raise_errors=True)
BatchServiceAIFeedbackInitiateCommandDataV1.model_rebuild(raise_errors=True)
BatchServiceCJAssessmentInitiateCommandDataV1.model_rebuild(raise_errors=True)
EssayLifecycleSpellcheckRequestV1.model_rebuild(raise_errors=True)
EssayLifecycleNLPRequestV1.model_rebuild(raise_errors=True)
EssayLifecycleAIFeedbackRequestV1.model_rebuild(raise_errors=True)
