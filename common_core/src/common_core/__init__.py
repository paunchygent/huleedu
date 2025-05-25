"""
HuleEdu Common Core Package.
"""

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
try:
    BaseEventData.model_rebuild()
    EnhancedProcessingUpdate.model_rebuild()
    EventTracker.model_rebuild()
    SpellcheckRequestedDataV1.model_rebuild()
    SpellcheckResultDataV1.model_rebuild()
except Exception:
    # If rebuild fails during import, that's okay
    pass
