"""
common_core.event_enums - Enums and helpers for the event-driven architecture.
"""

from __future__ import annotations

from enum import Enum


class ProcessingEvent(str, Enum):
    # -------------  Batch coordination events  -------------#
    BATCH_ESSAYS_REGISTERED = "batch.essays.registered"
    BATCH_ESSAYS_READY = "batch.essays.ready"
    # -------------  Essay lifecycle  -------------#
    ESSAY_PHASE_INITIATION_REQUESTED = "essay.phase.initiation.requested"
    ESSAY_LIFECYCLE_STATE_UPDATED = "essay.lifecycle.state.updated"
    # -------------  Essay content readiness  -------------#
    ESSAY_CONTENT_PROVISIONED = "essay.content.provisioned"
    EXCESS_CONTENT_PROVISIONED = "excess.content.provisioned"
    ESSAY_VALIDATION_FAILED = "essay.validation.failed"
    # -------------  Specialized service commands  -------------#
    BATCH_SPELLCHECK_INITIATE_COMMAND = "batch.spellcheck.initiate.command"
    BATCH_CJ_ASSESSMENT_INITIATE_COMMAND = "batch.cj_assessment.initiate.command"
    BATCH_AI_FEEDBACK_INITIATE_COMMAND = "batch.ai_feedback.initiate.command"
    BATCH_NLP_INITIATE_COMMAND = "batch.nlp.initiate.command"
    # -------------  ELS-BOS communication events  -------------#
    ELS_BATCH_PHASE_OUTCOME = "els.batch.phase.outcome"
    # -------------  Results from specialised services -############
    ESSAY_SPELLCHECK_COMPLETED = "essay.spellcheck.completed"
    ESSAY_SPELLCHECK_REQUESTED = "essay.spellcheck.requested"
    ELS_CJ_ASSESSMENT_REQUESTED = "els.cj_assessment.requested"
    CJ_ASSESSMENT_COMPLETED = "cj_assessment.completed"
    CJ_ASSESSMENT_FAILED = "cj_assessment.failed"
    ESSAY_NLP_COMPLETED = "essay.nlp.completed"
    ESSAY_AIFEEDBACK_COMPLETED = "essay.aifeedback.completed"
    ESSAY_EDITOR_REVISION_COMPLETED = "essay.editor_revision.completed"
    ESSAY_GRAMMAR_COMPLETED = "essay.grammar.completed"
    # -------------  Enhanced file and class management events  -------------#
    STUDENT_PARSING_COMPLETED = "student.parsing.completed"
    ESSAY_STUDENT_ASSOCIATION_UPDATED = "essay.student.association.updated"
    BATCH_FILE_ADDED = "batch.file.added"
    BATCH_FILE_REMOVED = "batch.file.removed"
    CLASS_CREATED = "class.created"
    STUDENT_CREATED = "student.created"
    # -------------  Student validation workflow events  -------------#
    STUDENT_ASSOCIATIONS_CONFIRMED = "student.associations.confirmed"
    VALIDATION_TIMEOUT_PROCESSED = "validation.timeout.processed"
    # -------------  Generic -------------#
    PROCESSING_STARTED = "processing.started"
    PROCESSING_CONCLUDED = "processing.concluded"
    PROCESSING_FAILED = "processing.failed"


# Private mapping for topic_name() function
_TOPIC_MAPPING = {
    ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED: "huleedu.essay.spellcheck.requested.v1",
    ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED: "huleedu.essay.spellcheck.completed.v1",
    ProcessingEvent.BATCH_ESSAYS_REGISTERED: "huleedu.batch.essays.registered.v1",
    ProcessingEvent.ESSAY_CONTENT_PROVISIONED: "huleedu.file.essay.content.provisioned.v1",
    ProcessingEvent.EXCESS_CONTENT_PROVISIONED: "huleedu.els.excess.content.provisioned.v1",
    ProcessingEvent.ESSAY_VALIDATION_FAILED: "huleedu.file.essay.validation.failed.v1",
    ProcessingEvent.BATCH_ESSAYS_READY: "huleedu.els.batch.essays.ready.v1",
    ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND: "huleedu.els.spellcheck.initiate.command.v1",
    ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND: (
        "huleedu.batch.cj_assessment.initiate.command.v1"
    ),
    ProcessingEvent.BATCH_AI_FEEDBACK_INITIATE_COMMAND: (
        "huleedu.batch.ai_feedback.initiate.command.v1"
    ),
    ProcessingEvent.BATCH_NLP_INITIATE_COMMAND: ("huleedu.batch.nlp.initiate.command.v1"),
    ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED: "huleedu.els.cj_assessment.requested.v1",
    ProcessingEvent.CJ_ASSESSMENT_COMPLETED: "huleedu.cj_assessment.completed.v1",
    ProcessingEvent.CJ_ASSESSMENT_FAILED: "huleedu.cj_assessment.failed.v1",
    ProcessingEvent.ELS_BATCH_PHASE_OUTCOME: "huleedu.els.batch_phase.outcome.v1",
    ProcessingEvent.STUDENT_PARSING_COMPLETED: "huleedu.file.student.parsing.completed.v1",
    ProcessingEvent.ESSAY_STUDENT_ASSOCIATION_UPDATED: "huleedu.class.essay.association.updated.v1",
    ProcessingEvent.BATCH_FILE_ADDED: "huleedu.file.batch.file.added.v1",
    ProcessingEvent.BATCH_FILE_REMOVED: "huleedu.file.batch.file.removed.v1",
    ProcessingEvent.CLASS_CREATED: "huleedu.class.created.v1",
    ProcessingEvent.STUDENT_CREATED: "huleedu.class.student.created.v1",
    ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED: (
        "huleedu.class.student.associations.confirmed.v1"
    ),
    ProcessingEvent.VALIDATION_TIMEOUT_PROCESSED: "huleedu.class.validation.timeout.processed.v1",
}


def topic_name(event: ProcessingEvent) -> str:
    """
    Convert a ProcessingEvent to its corresponding Kafka topic name.
    """
    if event not in _TOPIC_MAPPING:
        mapped_events_summary = "\n".join(
            [f"- {e.name} ({e.value}) ➜ '{t}'" for e, t in _TOPIC_MAPPING.items()],
        )
        raise ValueError(
            f"Event '{event.name} ({event.value})' does not have an explicit topic mapping. "
            f"All events intended for Kafka must have deliberate topic contracts defined. "
            f"Currently mapped events:\n{mapped_events_summary}",
        )
    return _TOPIC_MAPPING[event]
