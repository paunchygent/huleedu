"""common_core.enums  – **Canonical enumeration catalogue**

Keep this file focused and stable.  Do **not** import heavy packages here; enums must
be import-time lightweight for every service.
"""

from __future__ import annotations

from enum import Enum
from typing import Set

# ---------------------------------------------------------------------------
# System-level lifecycle stages
# ---------------------------------------------------------------------------


class ProcessingStage(str, Enum):
    PENDING = "pending"
    INITIALIZED = "initialized"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def terminal(cls) -> Set["ProcessingStage"]:
        return {cls.COMPLETED, cls.FAILED, cls.CANCELLED}

    @classmethod
    def active(cls) -> Set["ProcessingStage"]:
        return {cls.PENDING, cls.INITIALIZED, cls.PROCESSING}


# ---------------------------------------------------------------------------
# Event names (Kafka / Redis topics use these exact strings)
# ---------------------------------------------------------------------------


class ProcessingEvent(str, Enum):
    # -------------  Batch orchestration -############
    BATCH_PIPELINE_REQUESTED = "batch.pipeline.requested"
    BATCH_PHASE_INITIATED = "batch.phase.initiated"
    BATCH_PIPELINE_PROGRESS_UPDATED = "batch.pipeline.progress.updated"
    BATCH_PHASE_CONCLUDED = "batch.phase.concluded"
    BATCH_LIFECYCLE_COMPLETED = "batch.lifecycle.completed"
    BATCH_LIFECYCLE_FAILED = "batch.lifecycle.failed"
    BATCH_LIFECYCLE_PARTIALLY_COMPLETED = "batch.lifecycle.partially_completed"

    # -------------  Essay lifecycle  -------------#
    ESSAY_PHASE_INITIATION_REQUESTED = "essay.phase.initiation.requested"
    ESSAY_LIFECYCLE_STATE_UPDATED = "essay.lifecycle.state.updated"

    # -------------  Results from specialised services -############
    ESSAY_SPELLCHECK_RESULT_RECEIVED = (
        "essay.spellcheck.result.received"  # Output from spellchecker
    )
    ESSAY_SPELLCHECK_REQUESTED = (
        "essay.spellcheck.requested"  # Input to spellchecker (added for clarity)
    )
    ESSAY_NLP_RESULT_RECEIVED = "essay.nlp.result.received"
    ESSAY_AIFEEDBACK_RESULT_RECEIVED = "essay.aifeedback.result.received"
    ESSAY_EDITOR_REVISION_RESULT_RECEIVED = "essay.editor_revision.result.received"
    ESSAY_GRAMMAR_RESULT_RECEIVED = "essay.grammar.result.received"

    # -------------  Generic -------------#
    PROCESSING_STARTED = "processing.started"
    PROCESSING_COMPLETED = "processing.completed"
    PROCESSING_FAILED = "processing.failed"


# Private mapping for topic_name() function
_TOPIC_MAPPING = {
    ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED: "huleedu.essay.spellcheck.requested.v1",
    ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED: "huleedu.essay.spellcheck.completed.v1",
    # Add more mappings as needed for other events - EACH MUST BE EXPLICIT
}


def topic_name(event: ProcessingEvent) -> str:
    """
    Convert a ProcessingEvent to its corresponding Kafka topic name.

    This centralizes topic naming. All events intended for Kafka MUST have an
    explicit mapping here to enforce architectural discipline.

    Args:
        event: The ProcessingEvent enum value.

    Returns:
        The Kafka topic name string.

    Raises:
        ValueError: If the event does not have an explicit topic mapping.

    Current Topic Mapping:
    ----------------------
    ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED ➜ "huleedu.essay.spellcheck.requested.v1"
    ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED ➜ "huleedu.essay.spellcheck.completed.v1"

    Example:
        topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED) ->
            "huleedu.essay.spellcheck.requested.v1"
    """
    if event not in _TOPIC_MAPPING:
        mapped_events_summary = "\n".join(
            [f"- {e.name} ({e.value}) ➜ '{t}'" for e, t in _TOPIC_MAPPING.items()]
        )
        raise ValueError(
            f"Event '{event.name} ({event.value})' does not have an explicit topic mapping. "
            f"All events intended for Kafka must have deliberate topic contracts defined. "
            f"Currently mapped events:\n{mapped_events_summary}"
        )
    return _TOPIC_MAPPING[event]


# ---------------------------------------------------------------------------
# Fine-grained essay status values (granular state machine)
# ---------------------------------------------------------------------------


class EssayStatus(str, Enum):
    UPLOADED = "uploaded"
    TEXT_EXTRACTED = "text_extracted"
    AWAITING_SPELLCHECK = "awaiting_spellcheck"
    SPELLCHECKING_IN_PROGRESS = "spellchecking_in_progress"
    SPELLCHECKED_SUCCESS = "spellchecked_success"
    SPELLCHECK_FAILED = "spellcheck_failed"
    AWAITING_NLP = "awaiting_nlp"
    NLP_IN_PROGRESS = "nlp_processing_in_progress"
    NLP_COMPLETED_SUCCESS = "nlp_completed_success"
    NLP_FAILED = "nlp_failed"
    AWAITING_AI_FEEDBACK = "awaiting_ai_feedback"
    AI_FEEDBACK_IN_PROGRESS = "ai_feedback_processing_in_progress"
    AI_FEEDBACK_COMPLETED_SUCCESS = "ai_feedback_completed_success"
    AI_FEEDBACK_FAILED = "ai_feedback_failed"
    AWAITING_EDITOR_REVISION = "awaiting_editor_revision"
    EDITOR_REVISION_IN_PROGRESS = "editor_revision_processing_in_progress"
    EDITOR_REVISION_COMPLETED_SUCCESS = "editor_revision_completed_success"
    EDITOR_REVISION_FAILED = "editor_revision_failed"
    AWAITING_GRAMMAR_CHECK = "awaiting_grammar_check"
    GRAMMAR_CHECK_IN_PROGRESS = "grammar_check_processing_in_progress"
    GRAMMAR_CHECK_COMPLETED_SUCCESS = "grammar_check_completed_success"
    GRAMMAR_CHECK_FAILED = "grammar_check_failed"
    AWAITING_CJ_INCLUSION = "awaiting_cj_inclusion"
    CJ_PROCESSING_ACTIVE = "cj_processing_active"
    CJ_RANKING_COMPLETED = "cj_ranking_completed"
    CJ_PROCESSING_FAILED = "cj_processing_failed"
    ESSAY_ALL_PROCESSING_COMPLETED = "essay_all_processing_completed"
    ESSAY_PARTIALLY_PROCESSED_WITH_FAILURES = "essay_partially_processed_with_failures"
    ESSAY_CRITICAL_FAILURE = "essay_critical_failure"


# ---------------------------------------------------------------------------
# Batch status
# ---------------------------------------------------------------------------


class BatchStatus(str, Enum):
    UPLOADED = "uploaded"
    PARTIALLY_UPLOADED = "partially_uploaded"
    PENDING_CONFIGURATION = "pending_configuration"
    PENDING_PROCESSING_INITIATION = "pending_processing_initiation"
    PROCESSING_CONTENT_ENRICHMENT = "processing_content_enrichment"
    AWAITING_CJ_ASSESSMENT = "awaiting_cj_assessment"
    PROCESSING_CJ_ASSESSMENT = "processing_cj_assessment"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Content types
# ---------------------------------------------------------------------------


class ContentType(str, Enum):
    ORIGINAL_ESSAY = "original_essay"
    CORRECTED_TEXT = "corrected_text"
    PROCESSING_LOG = "processing_log"
    NLP_METRICS_JSON = "nlp_metrics_json"
    STUDENT_FACING_AI_FEEDBACK_TEXT = "student_facing_ai_feedback_text"
    AI_EDITOR_REVISION_TEXT = "ai_editor_revision_text"
    AI_DETAILED_ANALYSIS_JSON = "ai_detailed_analysis_json"
    GRAMMAR_ANALYSIS_JSON = "grammar_analysis_json"
    CJ_RESULTS_JSON = "cj_results_json"


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------


class ErrorCode(str, Enum):
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    KAFKA_PUBLISH_ERROR = "KAFKA_PUBLISH_ERROR"
    CONTENT_SERVICE_ERROR = "CONTENT_SERVICE_ERROR"
    SPELLCHECK_SERVICE_ERROR = "SPELLCHECK_SERVICE_ERROR"
    NLP_SERVICE_ERROR = "NLP_SERVICE_ERROR"
    AI_FEEDBACK_SERVICE_ERROR = "AI_FEEDBACK_SERVICE_ERROR"
    CJ_ASSESSMENT_SERVICE_ERROR = "CJ_ASSESSMENT_SERVICE_ERROR"
