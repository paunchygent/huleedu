"""
common_core.event_enums - Enums and helpers for the event-driven architecture.
"""

from __future__ import annotations

from enum import Enum


class ProcessingEvent(str, Enum):
    # -------------  Batch coordination events  -------------#
    BATCH_ESSAYS_REGISTERED = "batch.essays.registered"
    BATCH_ESSAYS_READY = "batch.essays.ready"
    BATCH_PIPELINE_COMPLETED = "batch.pipeline.completed"
    BATCH_PHASE_SKIPPED = "batch.phase.skipped"
    # -------------  Essay lifecycle  -------------#
    ESSAY_PHASE_INITIATION_REQUESTED = "essay.phase.initiation.requested"
    ESSAY_LIFECYCLE_STATE_UPDATED = "essay.lifecycle.state.updated"
    ESSAY_SLOT_ASSIGNED = "essay.slot.assigned"
    # -------------  Essay content readiness  -------------#
    ESSAY_CONTENT_PROVISIONED = "essay.content.provisioned"
    EXCESS_CONTENT_PROVISIONED = "excess.content.provisioned"
    ESSAY_VALIDATION_FAILED = "essay.validation.failed"
    # -------------  Phase 1 content and matching coordination  -------------#
    BATCH_CONTENT_PROVISIONING_COMPLETED = "batch.content.provisioning.completed"
    BATCH_STUDENT_MATCHING_INITIATE_COMMAND = "batch.student.matching.initiate.command"
    BATCH_STUDENT_MATCHING_REQUESTED = "batch.student.matching.requested"
    # -------------  Specialized service commands  -------------#
    BATCH_SPELLCHECK_INITIATE_COMMAND = "batch.spellcheck.initiate.command"
    BATCH_CJ_ASSESSMENT_INITIATE_COMMAND = "batch.cj_assessment.initiate.command"
    BATCH_AI_FEEDBACK_INITIATE_COMMAND = "batch.ai_feedback.initiate.command"
    BATCH_NLP_INITIATE_COMMAND = "batch.nlp.initiate.command"
    # -------------  ELS-BOS communication events  -------------#
    ELS_BATCH_PHASE_OUTCOME = "els.batch.phase.outcome"
    BATCH_VALIDATION_ERRORS = "batch.validation.errors"
    # -------------  Client commands  -------------#
    CLIENT_BATCH_PIPELINE_REQUEST = "client.batch.pipeline.request"
    # -------------  Results from specialised services -############
    ESSAY_SPELLCHECK_COMPLETED = "essay.spellcheck.completed"
    ESSAY_SPELLCHECK_REQUESTED = "essay.spellcheck.requested"
    BATCH_NLP_PROCESSING_REQUESTED = "batch.nlp.processing.requested"
    ELS_CJ_ASSESSMENT_REQUESTED = "els.cj_assessment.requested"
    CJ_ASSESSMENT_COMPLETED = "cj_assessment.completed"
    CJ_ASSESSMENT_FAILED = "cj_assessment.failed"
    ESSAY_NLP_COMPLETED = "essay.nlp.completed"
    BATCH_NLP_ANALYSIS_COMPLETED = "batch.nlp.analysis.completed"
    BATCH_AUTHOR_MATCHES_SUGGESTED = "batch.author.matches.suggested"
    ESSAY_AIFEEDBACK_COMPLETED = "essay.aifeedback.completed"
    ESSAY_EDITOR_REVISION_COMPLETED = "essay.editor_revision.completed"
    ESSAY_GRAMMAR_COMPLETED = "essay.grammar.completed"
    # -------------  Enhanced file and class management events  -------------#
    ESSAY_STUDENT_ASSOCIATION_UPDATED = "essay.student.association.updated"
    BATCH_FILE_ADDED = "batch.file.added"
    BATCH_FILE_REMOVED = "batch.file.removed"
    CLASS_CREATED = "class.created"
    CLASS_UPDATED = "class.updated"
    STUDENT_CREATED = "student.created"
    STUDENT_UPDATED = "student.updated"
    # -------------  Student validation workflow events  -------------#
    STUDENT_ASSOCIATIONS_CONFIRMED = "student.associations.confirmed"
    VALIDATION_TIMEOUT_PROCESSED = "validation.timeout.processed"
    # -------------  Teacher notification events  -------------#
    TEACHER_NOTIFICATION_REQUESTED = "teacher.notification.requested"
    # -------------  Result aggregator events  -------------#
    BATCH_RESULTS_READY = "batch.results.ready"
    BATCH_ASSESSMENT_COMPLETED = "batch.assessment.completed"
    ASSESSMENT_RESULT_PUBLISHED = "assessment.result.published"
    # -------------  Generic -------------#
    PROCESSING_STARTED = "processing.started"
    PROCESSING_CONCLUDED = "processing.concluded"
    PROCESSING_FAILED = "processing.failed"
    # -------------  LLM Provider events  -------------#
    LLM_REQUEST_STARTED = "llm_provider.request.started"
    LLM_REQUEST_COMPLETED = "llm_provider.request.completed"
    LLM_PROVIDER_FAILURE = "llm_provider.failure"
    LLM_USAGE_ANALYTICS = "llm_provider.usage.analytics"
    LLM_COST_ALERT = "llm_provider.cost.alert"
    LLM_COST_TRACKING = "llm_provider.cost.tracking"
    LLM_COMPARISON_RESULT = "llm_provider.comparison_result"


# Private mapping for topic_name() function
_TOPIC_MAPPING = {
    ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED: "huleedu.essay.spellcheck.requested.v1",
    ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED: "huleedu.essay.spellcheck.completed.v1",
    ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED: "huleedu.batch.nlp.processing.requested.v1",
    ProcessingEvent.BATCH_ESSAYS_REGISTERED: "huleedu.batch.essays.registered.v1",
    ProcessingEvent.BATCH_PIPELINE_COMPLETED: "huleedu.batch.pipeline.completed.v1",
    ProcessingEvent.BATCH_PHASE_SKIPPED: "huleedu.batch.phase.skipped.v1",
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
    ProcessingEvent.BATCH_CONTENT_PROVISIONING_COMPLETED: (
        "huleedu.batch.content.provisioning.completed.v1"
    ),
    ProcessingEvent.BATCH_STUDENT_MATCHING_INITIATE_COMMAND: (
        "huleedu.batch.student.matching.initiate.command.v1"
    ),
    ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED: "huleedu.batch.student.matching.requested.v1",
    ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED: "huleedu.batch.author.matches.suggested.v1",
    ProcessingEvent.ESSAY_NLP_COMPLETED: "huleedu.essay.nlp.completed.v1",
    ProcessingEvent.BATCH_NLP_ANALYSIS_COMPLETED: "huleedu.batch.nlp.analysis.completed.v1",
    ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED: "huleedu.els.cj_assessment.requested.v1",
    ProcessingEvent.CJ_ASSESSMENT_COMPLETED: "huleedu.cj_assessment.completed.v1",
    ProcessingEvent.CJ_ASSESSMENT_FAILED: "huleedu.cj_assessment.failed.v1",
    ProcessingEvent.ELS_BATCH_PHASE_OUTCOME: "huleedu.els.batch.phase.outcome.v1",
    ProcessingEvent.ESSAY_STUDENT_ASSOCIATION_UPDATED: "huleedu.class.essay.association.updated.v1",
    ProcessingEvent.BATCH_FILE_ADDED: "huleedu.file.batch.file.added.v1",
    ProcessingEvent.BATCH_FILE_REMOVED: "huleedu.file.batch.file.removed.v1",
    ProcessingEvent.CLASS_CREATED: "huleedu.class.created.v1",
    ProcessingEvent.CLASS_UPDATED: "huleedu.class.updated.v1",
    ProcessingEvent.STUDENT_CREATED: "huleedu.class.student.created.v1",
    ProcessingEvent.STUDENT_UPDATED: "huleedu.class.student.updated.v1",
    ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED: (
        "huleedu.class.student.associations.confirmed.v1"
    ),
    ProcessingEvent.VALIDATION_TIMEOUT_PROCESSED: "huleedu.class.validation.timeout.processed.v1",
    ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED: "huleedu.notification.teacher.requested.v1",
    ProcessingEvent.ESSAY_SLOT_ASSIGNED: "huleedu.els.essay.slot.assigned.v1",
    # Result aggregator events
    ProcessingEvent.BATCH_RESULTS_READY: "huleedu.ras.batch.results.ready.v1",
    ProcessingEvent.BATCH_ASSESSMENT_COMPLETED: "huleedu.ras.batch.assessment.completed.v1",
    ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED: "huleedu.assessment.results.v1",
    # LLM Provider events
    ProcessingEvent.LLM_REQUEST_STARTED: "huleedu.llm_provider.request_started.v1",
    ProcessingEvent.LLM_REQUEST_COMPLETED: "huleedu.llm_provider.request_completed.v1",
    ProcessingEvent.LLM_PROVIDER_FAILURE: "huleedu.llm_provider.failure.v1",
    ProcessingEvent.LLM_USAGE_ANALYTICS: "huleedu.llm_provider.usage_analytics.v1",
    ProcessingEvent.LLM_COST_ALERT: "huleedu.llm_provider.cost_alert.v1",
    ProcessingEvent.LLM_COST_TRACKING: "huleedu.llm_provider.cost_tracking.v1",
    ProcessingEvent.LLM_COMPARISON_RESULT: "huleedu.llm_provider.comparison_result.v1",
    # New dual-event architecture topics
    ProcessingEvent.BATCH_VALIDATION_ERRORS: "huleedu.els.batch.validation.errors.v1",
    ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST: "huleedu.commands.batch.pipeline.v1",
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
