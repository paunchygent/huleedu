"""
HuleEdu Common Core Package.
"""

# Required for Pydantic model rebuilding - Union is used in forward references
# in base_event_models.py and must be available when model_rebuild() is called
from typing import Union

from .enums import (
    BatchStatus,
    ContentType,
    ErrorCode,
    EssayStatus,
    ProcessingEvent,
    ProcessingStage,
    topic_name,
)
from .events.base_event_models import (
    BaseEventData,
    EnhancedProcessingUpdate,
    EventTracker,
)
from .events.envelope import EventEnvelope
from .events.spellcheck_models import SpellcheckRequestedDataV1, SpellcheckResultDataV1
from .metadata_models import (
    AIFeedbackMetadata,
    BatchProcessingMetadata,
    CancellationMetadata,
    EntityReference,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
    TaskProcessingMetadata,
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
    "BatchProcessingMetadata",
    "AIFeedbackMetadata",
    "StorageReferenceMetadata",
    "TaskProcessingMetadata",
    "UserActivityMetadata",
    "CancellationMetadata",
    # Pipeline Models
    "PipelineExecutionStatus",
    "EssayProcessingCounts",
    "PipelineStateDetail",
    "ProcessingPipelineState",
    # Event Infrastructure
    "EventEnvelope",
    "BaseEventData",
    "EnhancedProcessingUpdate",
    "EventTracker",
    # Specific Event Data Models
    "SpellcheckRequestedDataV1",
    "SpellcheckResultDataV1",
]

# Rebuild models to resolve forward references after all imports
# Now that all enums are imported above, forward references should resolve successfully
BaseEventData.model_rebuild(raise_errors=True)
EnhancedProcessingUpdate.model_rebuild(raise_errors=True)
EventTracker.model_rebuild(raise_errors=True)
SpellcheckRequestedDataV1.model_rebuild(raise_errors=True)
SpellcheckResultDataV1.model_rebuild(raise_errors=True)
