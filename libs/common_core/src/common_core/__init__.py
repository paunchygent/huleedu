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
from .config_enums import Environment, LLMProviderType
from .domain_enums import (
    ContentType,
    CourseCode,
    EssayComparisonWinner,
    Language,
    get_course_language,
    get_course_level,
    get_course_name,
)
from .error_enums import ClassManagementErrorCode, ErrorCode, FileValidationErrorCode
from .essay_service_models import (
    EssayLifecycleAIFeedbackRequestV1,
    EssayLifecycleNLPRequestV1,
    EssayLifecycleSpellcheckRequestV1,
)
from .event_enums import ProcessingEvent, topic_name
from .events.ai_feedback_events import AIFeedbackInputDataV1
from .events.base_event_models import (
    BaseEventData,
    EventTracker,
    ProcessingUpdate,
)
from .events.batch_coordination_events import (
    BatchEssaysReady,
    BatchEssaysRegistered,
    BatchReadinessTimeout,
    ExcessContentProvisionedV1,
)
from .events.cj_assessment_events import (
    CJAssessmentCompletedV1,
    CJAssessmentFailedV1,
    ELS_CJAssessmentRequestV1,
)
from .events.envelope import EventEnvelope
from .events.file_events import (
    EssayContentProvisionedV1,
    EssayValidationFailedV1,
)
from .events.llm_provider_events import (
    LLMComparisonResultV1,
    LLMCostAlertV1,
    LLMCostTrackingV1,
    LLMProviderFailureV1,
    LLMRequestCompletedV1,
    LLMRequestStartedV1,
    LLMUsageAnalyticsV1,
    TokenUsage,
)
from .events.nlp_events import EssayAuthorMatchSuggestedV1, StudentMatchSuggestion
from .events.spellcheck_models import SpellcheckRequestedDataV1, SpellcheckResultDataV1
from .metadata_models import (
    EntityReference,
    EssayProcessingInputRefV1,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)
from .models.error_models import ErrorDetail
from .observability_enums import CacheOperation, MetricName, OperationType
from .pipeline_models import (
    EssayProcessingCounts,
    PhaseName,
    PipelineExecutionStatus,
    PipelineStateDetail,
    ProcessingPipelineState,
)
from .status_enums import (
    BatchStatus,
    CacheStatus,
    CircuitBreakerState,
    EssayStatus,
    OperationStatus,
    ProcessingStage,
    ProcessingStatus,
    QueueStatus,
    ValidationStatus,
)

__all__ = [
    # Status Enums
    "ProcessingStage",
    "EssayStatus",
    "BatchStatus",
    "ProcessingStatus",
    "ValidationStatus",
    "OperationStatus",
    "CacheStatus",
    "CircuitBreakerState",
    "QueueStatus",
    # Domain Enums
    "ContentType",
    "CourseCode",
    "EssayComparisonWinner",
    "Language",
    "get_course_language",
    "get_course_name",
    "get_course_level",
    # Event Enums
    "ProcessingEvent",
    "topic_name",
    # Observability Enums
    "MetricName",
    "OperationType",
    "CacheOperation",
    # Error Enums
    "ErrorCode",
    "FileValidationErrorCode",
    "ClassManagementErrorCode",
    "ErrorDetail",
    # Config Enums
    "Environment",
    "LLMProviderType",
    # Metadata Models
    "EntityReference",
    "SystemProcessingMetadata",
    "StorageReferenceMetadata",
    "EssayProcessingInputRefV1",
    # Pipeline Models
    "PhaseName",
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
    "ELS_CJAssessmentRequestV1",
    "CJAssessmentCompletedV1",
    "CJAssessmentFailedV1",
    # Batch Coordination Event Models
    "BatchEssaysRegistered",
    "BatchEssaysReady",
    "BatchReadinessTimeout",
    "ExcessContentProvisionedV1",
    # File Service Event Models
    "EssayContentProvisionedV1",
    "EssayValidationFailedV1",
    # NLP Service Event Models
    "EssayAuthorMatchSuggestedV1",
    "StudentMatchSuggestion",
    # LLM Provider Event Models
    "LLMComparisonResultV1",
    "LLMCostAlertV1",
    "LLMCostTrackingV1",
    "LLMProviderFailureV1",
    "LLMRequestCompletedV1",
    "LLMRequestStartedV1",
    "LLMUsageAnalyticsV1",
    "TokenUsage",
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
BatchEssaysRegistered.model_rebuild(raise_errors=True)
BatchEssaysReady.model_rebuild(raise_errors=True)
BatchReadinessTimeout.model_rebuild(raise_errors=True)
ExcessContentProvisionedV1.model_rebuild(raise_errors=True)
EssayContentProvisionedV1.model_rebuild(raise_errors=True)
EssayValidationFailedV1.model_rebuild(raise_errors=True)
ELS_CJAssessmentRequestV1.model_rebuild(raise_errors=True)
CJAssessmentCompletedV1.model_rebuild(raise_errors=True)
CJAssessmentFailedV1.model_rebuild(raise_errors=True)
LLMComparisonResultV1.model_rebuild(raise_errors=True)
TokenUsage.model_rebuild(raise_errors=True)
EssayAuthorMatchSuggestedV1.model_rebuild(raise_errors=True)
StudentMatchSuggestion.model_rebuild(raise_errors=True)
