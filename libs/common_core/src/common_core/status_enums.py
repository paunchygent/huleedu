"""Status enums for lifecycle, processing, and operation state machines.

ProcessingStage: Generic processing lifecycle (used in ProcessingUpdate events).
EssayStatus: Fine-grained essay state machine through pipeline.
BatchStatus: Batch-level state machine (GUEST vs REGULAR flows).
BatchClientStatus: Simplified client-facing batch status.

See: libs/common_core/docs/status-state-machines.md
"""

from __future__ import annotations

from enum import Enum


# --- System-level lifecycle stages ---
class ProcessingStage(str, Enum):
    """Generic processing lifecycle stages for thin events (ProcessingUpdate).

    Used in state-tracking events (CJAssessmentCompletedV1, etc.). Represents
    high-level processing outcome: success, failure, or cancellation.

    terminal() returns states that end processing (COMPLETED, FAILED, CANCELLED).
    active() returns non-terminal states (COMPLETED, INITIALIZED, PROCESSING).

    See: libs/common_core/docs/dual-event-pattern.md
    """

    PENDING = "pending"
    INITIALIZED = "initialized"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def terminal(cls) -> set[ProcessingStage]:
        """Return terminal states (no further processing)."""
        return {cls.COMPLETED, cls.FAILED, cls.CANCELLED}

    @classmethod
    def active(cls) -> set[ProcessingStage]:
        """Return active (non-cancelled) states."""
        return {cls.COMPLETED, cls.INITIALIZED, cls.PROCESSING}


# --- Fine-grained essay status values (granular state machine) ---
class EssayStatus(str, Enum):
    """Fine-grained essay state machine through processing pipeline.

    Tracks essay from upload through all processing phases (spellcheck, NLP, CJ, etc.).
    Each phase has AWAITING, IN_PROGRESS, SUCCESS, FAILED states.

    Terminal states: ALL_PROCESSING_COMPLETED, ESSAY_CRITICAL_FAILURE.

    See: libs/common_core/docs/status-state-machines.md
    """

    # File Service Results Statuses
    UPLOADED = "uploaded"
    TEXT_EXTRACTED = "text_extracted"
    # Content Ingestion Statuses
    CONTENT_INGESTING = "content_ingesting"
    CONTENT_INGESTION_FAILED = "content_ingestion_failed"
    # ELS Pipeline Management Statuses
    READY_FOR_PROCESSING = "ready_for_processing"
    # Spellcheck Statuses
    AWAITING_SPELLCHECK = "awaiting_spellcheck"
    SPELLCHECKING_IN_PROGRESS = "spellchecking_in_progress"
    SPELLCHECKED_SUCCESS = "spellchecked_success"
    SPELLCHECK_FAILED = "spellcheck_failed"
    # NLP Statuses
    AWAITING_NLP = "awaiting_nlp"
    NLP_IN_PROGRESS = "nlp_processing_in_progress"
    NLP_SUCCESS = "nlp_success"
    NLP_FAILED = "nlp_failed"
    # AI Feedback Statuses
    AWAITING_AI_FEEDBACK = "awaiting_ai_feedback"
    AI_FEEDBACK_IN_PROGRESS = "ai_feedback_processing_in_progress"
    AI_FEEDBACK_SUCCESS = "ai_feedback_success"
    AI_FEEDBACK_FAILED = "ai_feedback_failed"
    # Editor Revision Statuses
    AWAITING_EDITOR_REVISION = "awaiting_editor_revision"
    EDITOR_REVISION_IN_PROGRESS = "editor_revision_processing_in_progress"
    EDITOR_REVISION_SUCCESS = "editor_revision_success"
    EDITOR_REVISION_FAILED = "editor_revision_failed"
    # Grammar Check Statuses
    AWAITING_GRAMMAR_CHECK = "awaiting_grammar_check"
    GRAMMAR_CHECK_IN_PROGRESS = "grammar_check_processing_in_progress"
    GRAMMAR_CHECK_SUCCESS = "grammar_check_success"
    GRAMMAR_CHECK_FAILED = "grammar_check_failed"
    # CJ Assessment Statuses
    AWAITING_CJ_ASSESSMENT = "awaiting_cj_assessment"
    CJ_ASSESSMENT_IN_PROGRESS = "cj_assessment_processing_in_progress"
    CJ_ASSESSMENT_SUCCESS = "cj_assessment_success"
    CJ_ASSESSMENT_FAILED = "cj_assessment_failed"
    # Pipeline Completion Status
    ALL_PROCESSING_COMPLETED = "all_processing_completed"
    # Status for critical failures do to other reasons than pipeline failures
    ESSAY_CRITICAL_FAILURE = "essay_critical_failure"


# --- Batch status ---
class BatchStatus(str, Enum):
    """Batch-level state machine for GUEST and REGULAR batch flows.

    GUEST flow: AWAITING_CONTENT_VALIDATION → AWAITING_PIPELINE_CONFIGURATION →
    READY_FOR_PIPELINE_EXECUTION → PROCESSING_PIPELINES → terminal.

    REGULAR flow: AWAITING_CONTENT_VALIDATION → AWAITING_STUDENT_VALIDATION →
    STUDENT_VALIDATION_COMPLETED → READY_FOR_PIPELINE_EXECUTION →
    PROCESSING_PIPELINES → terminal.

    Terminal states: COMPLETED_SUCCESSFULLY, COMPLETED_WITH_FAILURES,
    FAILED_CRITICALLY, CANCELLED.

    See: libs/common_core/docs/status-state-machines.md
    """

    AWAITING_CONTENT_VALIDATION = "awaiting_content_validation"
    CONTENT_INGESTION_FAILED = "content_ingestion_failed"
    AWAITING_PIPELINE_CONFIGURATION = "awaiting_pipeline_configuration"
    READY_FOR_PIPELINE_EXECUTION = "ready_for_pipeline_execution"
    PROCESSING_PIPELINES = "processing_pipelines"
    AWAITING_STUDENT_VALIDATION = "awaiting_student_validation"
    STUDENT_VALIDATION_COMPLETED = "student_validation_completed"
    VALIDATION_TIMEOUT_PROCESSED = "validation_timeout_processed"
    COMPLETED_SUCCESSFULLY = "completed_successfully"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    FAILED_CRITICALLY = "failed_critically"
    CANCELLED = "cancelled"


# --- Generic Statuses (New) ---
class BatchClientStatus(str, Enum):
    """Client-facing batch status for API responses and WebSocket events.

    Simplified view of batch processing state for frontends. Synchronized between
    REST API and WebSocket notifications.

    Flow: PENDING_CONTENT → READY → PROCESSING →
    (COMPLETED_SUCCESSFULLY | COMPLETED_WITH_FAILURES | FAILED)

    Terminal: COMPLETED_SUCCESSFULLY, COMPLETED_WITH_FAILURES, FAILED, CANCELLED.
    """

    # Initial states - batch not yet ready for processing
    PENDING_CONTENT = "pending_content"  # Awaiting content validation or configuration

    # Ready state - batch configured and ready to process
    READY = "ready"  # Ready for pipeline execution

    # Active processing state
    PROCESSING = "processing"  # Currently being processed (any pipeline phase)

    # Terminal success states
    COMPLETED_SUCCESSFULLY = "completed_successfully"  # All essays processed successfully
    COMPLETED_WITH_FAILURES = "completed_with_failures"  # Some essays failed, batch complete

    # Terminal failure states
    FAILED = "failed"  # Critical failure, processing stopped
    CANCELLED = "cancelled"  # Processing cancelled by user or system


class ProcessingStatus(str, Enum):
    """Generic processing status (simpler than ProcessingStage)."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationStatus(str, Enum):
    """Validation operation outcomes."""

    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"


class OperationStatus(str, Enum):
    """Operation outcomes for metrics collection."""

    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    NOT_FOUND = "not_found"


class CacheStatus(str, Enum):
    """Cache operation outcomes (Redis)."""

    OK = "ok"
    HIT = "hit"
    MISS = "miss"
    ERROR = "error"


# --- Spell-checker job status ---
class SpellcheckJobStatus(str, Enum):
    """Spellcheck job lifecycle in Spellchecker Service."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"


class QueueStatus(str, Enum):
    """LLM request queue status in LLM Provider Service."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    EXPIRED = "expired"
    FAILED = "failed"


class CircuitBreakerState(str, Enum):
    """Circuit breaker states for resilience patterns (huleedu_service_libs)."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failure threshold exceeded, blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


# --- CJ Assessment Batch State ---
class CJBatchStateEnum(str, Enum):
    """CJ assessment batch state machine (internal to CJ Service)."""

    INITIALIZING = "INITIALIZING"
    GENERATING_PAIRS = "GENERATING_PAIRS"
    WAITING_CALLBACKS = "WAITING_CALLBACKS"  # Awaiting LLM callbacks
    SCORING = "SCORING"  # Bradley-Terry calculation
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# --- Student Association Status ---
class StudentAssociationStatus(str, Enum):
    """Student-essay association status (Class Management Service, REGULAR batches only)."""

    PENDING_VALIDATION = "pending_validation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    TIMEOUT_CONFIRMED = "timeout_confirmed"  # Auto-confirmed after 24h
    NO_MATCH = "no_match"


class AssociationValidationMethod(str, Enum):
    """How student association was validated."""

    HUMAN = "human"  # Teacher manually confirmed
    TIMEOUT = "timeout"  # Auto-confirmed after timeout
    AUTO = "auto"  # High-confidence auto-match


class AssociationConfidenceLevel(str, Enum):
    """NLP student matching confidence levels."""

    HIGH = "high"  # >0.9
    MEDIUM = "medium"  # 0.7-0.9
    LOW = "low"  # <0.7
    NO_MATCH = "no_match"
