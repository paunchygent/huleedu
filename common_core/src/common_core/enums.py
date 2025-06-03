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
        return {cls.COMPLETED, cls.INITIALIZED, cls.PROCESSING}


# ---------------------------------------------------------------------------
# Event names (Kafka / Redis topics use these exact strings)
# ---------------------------------------------------------------------------


class ProcessingEvent(str, Enum):
    # -------------  Batch orchestration -############
    BATCH_PIPELINE_REQUESTED = "batch.pipeline.requested"
    BATCH_PHASE_INITIATED = "batch.phase.initiated"
    BATCH_PIPELINE_PROGRESS_UPDATED = "batch.pipeline.progress.updated"
    BATCH_PHASE_CONCLUDED = "batch.phase.concluded"

    # -------------  Batch coordination events  -------------#
    BATCH_ESSAYS_REGISTERED = "batch.essays.registered"
    BATCH_ESSAYS_READY = "batch.essays.ready"

    # -------------  Essay lifecycle  -------------#
    ESSAY_PHASE_INITIATION_REQUESTED = "essay.phase.initiation.requested"
    ESSAY_LIFECYCLE_STATE_UPDATED = "essay.lifecycle.state.updated"

    # -------------  Essay content readiness  -------------#
    ESSAY_CONTENT_PROVISIONED = "essay.content.provisioned"
    EXCESS_CONTENT_PROVISIONED = "excess.content.provisioned"

    # -------------  Specialized service commands  -------------#
    BATCH_SPELLCHECK_INITIATE_COMMAND = "batch.spellcheck.initiate.command"
    BATCH_CJ_ASSESSMENT_INITIATE_COMMAND = "batch.cj_assessment.initiate.command"

    # -------------  ELS-BOS communication events  -------------#
    ELS_BATCH_PHASE_OUTCOME = "els.batch.phase.outcome"

    # -------------  Results from specialised services -############
    ESSAY_SPELLCHECK_RESULT_RECEIVED = (
        "essay.spellcheck.result.received"  # Output from spellchecker
    )
    ESSAY_SPELLCHECK_REQUESTED = (
        "essay.spellcheck.requested"  # Input to spellchecker (added for clarity)
    )
    ELS_CJ_ASSESSMENT_REQUESTED = "els.cj_assessment.requested"
    CJ_ASSESSMENT_COMPLETED = "cj_assessment.completed"
    CJ_ASSESSMENT_FAILED = "cj_assessment.failed"
    ESSAY_NLP_RESULT_RECEIVED = "essay.nlp.result.received"
    ESSAY_AIFEEDBACK_RESULT_RECEIVED = "essay.aifeedback.result.received"
    ESSAY_EDITOR_REVISION_RESULT_RECEIVED = "essay.editor_revision.result.received"
    ESSAY_GRAMMAR_RESULT_RECEIVED = "essay.grammar.result.received"

    # -------------  Generic -------------#
    PROCESSING_STARTED = "processing.started"
    PROCESSING_CONCLUDED = "processing.concluded"
    PROCESSING_FAILED = "processing.failed"


# Private mapping for topic_name() function
_TOPIC_MAPPING = {
    ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED: "huleedu.essay.spellcheck.requested.v1",
    ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED: "huleedu.essay.spellcheck.completed.v1",
    ProcessingEvent.BATCH_ESSAYS_REGISTERED: "huleedu.batch.essays.registered.v1",
    ProcessingEvent.ESSAY_CONTENT_PROVISIONED: "huleedu.file.essay.content.provisioned.v1",
    ProcessingEvent.EXCESS_CONTENT_PROVISIONED: "huleedu.els.excess.content.provisioned.v1",
    ProcessingEvent.BATCH_ESSAYS_READY: "huleedu.els.batch.essays.ready.v1",
    ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND: "huleedu.els.spellcheck.initiate.command.v1",
    ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND: (
        "huleedu.batch.cj_assessment.initiate.command.v1"
    ),
    ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED: "huleedu.els.cj_assessment.requested.v1",
    ProcessingEvent.CJ_ASSESSMENT_COMPLETED: "huleedu.cj_assessment.completed.v1",
    ProcessingEvent.CJ_ASSESSMENT_FAILED: "huleedu.cj_assessment.failed.v1",
    ProcessingEvent.ELS_BATCH_PHASE_OUTCOME: "huleedu.els.batch_phase.outcome.v1",
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
    ProcessingEvent.BATCH_ESSAYS_REGISTERED ➜ "huleedu.batch.essays.registered.v1"


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
    # File Service Results Statuses
    UPLOADED = "uploaded"
    TEXT_EXTRACTED = "text_extracted"
    # Content Ingestion Statuses
    CONTENT_INGESTING = "content_ingester"
    CONTENT_INGESTION_FAILED = "content_ingestion_failed"
    # ELS Pipeline Management Statuses
    READY_FOR_PROCESSING = "ready_for_processing"  # Content validated, awaiting pipeline assignment
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


# ---------------------------------------------------------------------------
# Batch status
# ---------------------------------------------------------------------------


class BatchStatus(str, Enum):
    # Initial Ingestion & Validation Phase (BOS awaiting
    # a full content readiness report from ELS/FileService)

    AWAITING_CONTENT_VALIDATION = "awaiting_content_validation"
    # Batch created, content being ingested/validated.

    # Terminal states for the initial ingestion/validation phase
    CONTENT_INGESTION_FAILED = "content_ingestion_failed"  # Critical issue with content, batch
    # cannot proceed. (Terminal for this path)
    AWAITING_PIPELINE_CONFIGURATION = "awaiting_pipeline_configuration"
    # All content successfully ingested & validated by ELS/FileService;
    # Batch is now awaiting user to define/confirm the specific processing pipelines.
    # This replaces PENDING_CONFIGURATION to be more descriptive of what's next.

    # Configuration Complete, Ready for Processing Pipelines
    READY_FOR_PIPELINE_EXECUTION = "ready_for_pipeline_execution"
    # User has defined pipelines; batch is queued for BOS to start the first pipeline.

    # Active Processing Phase
    PROCESSING_PIPELINES = "processing_pipelines"
    # BOS is actively orchestrating one or more requested pipelines via ELS.

    # Terminal States for the Entire Batch Processing Lifecycle
    COMPLETED_SUCCESSFULLY = "completed_successfully"
    # All requested pipelines completed successfully.
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    # All requested pipelines finished, but some had non-critical essay/pipeline failures.
    FAILED_CRITICALLY = "failed_critically"
    # A critical failure stopped batch processing.
    CANCELLED = "cancelled"
    # Batch processing was explicitly cancelled.


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
