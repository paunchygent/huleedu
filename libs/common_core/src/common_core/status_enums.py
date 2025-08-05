"""
common_core.status_enums - Enums for lifecycle, processing, and operation statuses.
"""

from __future__ import annotations

from enum import Enum


# --- System-level lifecycle stages ---
class ProcessingStage(str, Enum):
    PENDING = "pending"
    INITIALIZED = "initialized"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def terminal(cls) -> set[ProcessingStage]:
        return {cls.COMPLETED, cls.FAILED, cls.CANCELLED}

    @classmethod
    def active(cls) -> set[ProcessingStage]:
        return {cls.COMPLETED, cls.INITIALIZED, cls.PROCESSING}


# --- Fine-grained essay status values (granular state machine) ---
class EssayStatus(str, Enum):
    # File Service Results Statuses
    UPLOADED = "uploaded"
    TEXT_EXTRACTED = "text_extracted"
    # Content Ingestion Statuses
    CONTENT_INGESTING = "content_ingester"
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
    """Defines the status of a batch as reported to the client."""

    AVAILABLE = "available"
    PROCESSING = "processing"


class ProcessingStatus(str, Enum):
    """Generic processing statuses."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationStatus(str, Enum):
    """Status codes for validation operations."""

    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"


class OperationStatus(str, Enum):
    """Status of operations for metrics collection."""

    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    NOT_FOUND = "not_found"


class CacheStatus(str, Enum):
    """Status codes for cache operations."""

    OK = "ok"
    HIT = "hit"
    MISS = "miss"
    ERROR = "error"


# --- Spell-checker job status ---
class SpellcheckJobStatus(str, Enum):
    """Lifecycle of a spell-checker job handled by spellchecker_service."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"


class QueueStatus(str, Enum):
    """Status codes for queued LLM requests."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    EXPIRED = "expired"
    FAILED = "failed"


class CircuitBreakerState(str, Enum):
    """States of the circuit breaker for resilience patterns."""

    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"  # Failure threshold exceeded, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


# --- CJ Assessment Batch State ---
class CJBatchStateEnum(str, Enum):
    """State machine for CJ assessment batch processing."""

    INITIALIZING = "INITIALIZING"  # Batch created, essays being prepared
    GENERATING_PAIRS = "GENERATING_PAIRS"  # Creating comparison pairs
    WAITING_CALLBACKS = "WAITING_CALLBACKS"  # Comparisons sent, awaiting results
    SCORING = "SCORING"  # Calculating Bradley-Terry scores
    COMPLETED = "COMPLETED"  # Successfully processed
    FAILED = "FAILED"  # Processing failed
    CANCELLED = "CANCELLED"  # Manually stopped


# --- Student Association Status ---
class StudentAssociationStatus(str, Enum):
    """Status of student-essay associations in Class Management Service."""

    PENDING_VALIDATION = "pending_validation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    TIMEOUT_CONFIRMED = "timeout_confirmed"
    NO_MATCH = "no_match"


class AssociationValidationMethod(str, Enum):
    """Method by which a student association was validated."""

    HUMAN = "human"
    TIMEOUT = "timeout"
    AUTO = "auto"


class AssociationConfidenceLevel(str, Enum):
    """Confidence level categories for student matching."""

    HIGH = "high"  # > 0.9 confidence
    MEDIUM = "medium"  # 0.7 - 0.9 confidence
    LOW = "low"  # < 0.7 confidence
    NO_MATCH = "no_match"  # No viable match found
