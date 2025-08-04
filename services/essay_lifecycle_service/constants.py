"""
Essay Lifecycle Service specific constants.

This module contains constants that are specific to ELS internal operations
and should not be shared across services. Shared domain constants belong
in common_core modules.
"""

from __future__ import annotations

from common_core.pipeline_models import PhaseName
from common_core.status_enums import EssayStatus

# ELS-specific phase status mapping for query operations
# Maps processing phases to their corresponding essay statuses for ELS coordination
ELS_PHASE_STATUS_MAPPING = {
    PhaseName.SPELLCHECK: [
        EssayStatus.AWAITING_SPELLCHECK,
        EssayStatus.SPELLCHECKING_IN_PROGRESS,
        EssayStatus.SPELLCHECKED_SUCCESS,
        EssayStatus.SPELLCHECK_FAILED,
    ],
    PhaseName.CJ_ASSESSMENT: [
        EssayStatus.AWAITING_CJ_ASSESSMENT,
        EssayStatus.CJ_ASSESSMENT_IN_PROGRESS,
        EssayStatus.CJ_ASSESSMENT_SUCCESS,
        EssayStatus.CJ_ASSESSMENT_FAILED,
    ],
    PhaseName.NLP: [
        EssayStatus.AWAITING_NLP,
        EssayStatus.NLP_IN_PROGRESS,
        EssayStatus.NLP_SUCCESS,
        EssayStatus.NLP_FAILED,
    ],
    PhaseName.AI_FEEDBACK: [
        EssayStatus.AWAITING_AI_FEEDBACK,
        EssayStatus.AI_FEEDBACK_IN_PROGRESS,
        EssayStatus.AI_FEEDBACK_SUCCESS,
        EssayStatus.AI_FEEDBACK_FAILED,
    ],
    # Note: STUDENT_MATCHING is handled via inter-service coordination
    # and does not have ELS-internal status transitions
}


def get_els_phase_statuses(phase_name: PhaseName | str) -> list[EssayStatus]:
    """
    Get valid essay statuses for an ELS-coordinated processing phase.

    Args:
        phase_name: The phase name (PhaseName enum or string)

    Returns:
        List of EssayStatus values for ELS-coordinated phases

    Raises:
        ValueError: If phase_name is not ELS-coordinated

    Example:
        >>> statuses = get_els_phase_statuses(PhaseName.SPELLCHECK)
        >>> assert EssayStatus.AWAITING_SPELLCHECK in statuses
    """
    # Convert string to PhaseName enum if needed
    if isinstance(phase_name, str):
        try:
            phase_name = PhaseName(phase_name)
        except ValueError:
            available_phases = list(ELS_PHASE_STATUS_MAPPING.keys())
            raise ValueError(
                f"Unknown phase '{phase_name}'. ELS-coordinated phases: {[p.value for p in available_phases]}"
            )

    if phase_name not in ELS_PHASE_STATUS_MAPPING:
        available_phases = list(ELS_PHASE_STATUS_MAPPING.keys())
        raise ValueError(
            f"Phase '{phase_name.value}' is not ELS-coordinated. "
            f"ELS-coordinated phases: {[p.value for p in available_phases]}"
        )

    return ELS_PHASE_STATUS_MAPPING[phase_name]


# Repository operation identifiers for logging and metrics
class RepositoryOperation:
    """Constants for repository operation identification in logs and metrics."""

    # Core CRUD operations
    CREATE_ESSAY_RECORD = "create_essay_record"
    UPDATE_ESSAY_STATE = "update_essay_state"
    GET_ESSAY_STATE = "get_essay_state"

    # Batch operations
    CREATE_ESSAY_RECORDS_BATCH = "create_essay_records_batch"
    LIST_ESSAYS_BY_BATCH = "list_essays_by_batch"
    LIST_ESSAYS_BY_BATCH_AND_PHASE = "list_essays_by_batch_and_phase"
    GET_BATCH_STATUS_SUMMARY = "get_batch_status_summary"
    GET_BATCH_SUMMARY_WITH_ESSAYS = "get_batch_summary_with_essays"

    # Specialized operations
    CREATE_WITH_CONTENT_IDEMPOTENCY = "create_essay_state_with_content_idempotency"
    CREATE_OR_UPDATE_FOR_SLOT_ASSIGNMENT = "create_or_update_essay_state_for_slot_assignment"
    GET_BY_TEXT_STORAGE_ID_AND_BATCH = "get_essay_by_text_storage_id_and_batch_id"
    UPDATE_ESSAY_PROCESSING_METADATA = "update_essay_processing_metadata"
    UPDATE_STUDENT_ASSOCIATION = "update_student_association"


# Processing metadata field keys used throughout ELS
class MetadataKey:
    """Constants for essay processing metadata field names."""

    # Core metadata
    ENTITY_TYPE = "entity_type"
    CREATED_VIA = "created_via"
    CURRENT_PHASE = "current_phase"
    COMMANDED_PHASES = "commanded_phases"

    # File and content metadata
    TEXT_STORAGE_ID = "text_storage_id"
    ORIGINAL_FILE_NAME = "original_file_name"
    FILE_SIZE = "file_size"
    FILE_SIZE_BYTES = "file_size_bytes"
    CONTENT_HASH = "content_hash"
    CONTENT_MD5_HASH = "content_md5_hash"
    SLOT_ASSIGNMENT_TIMESTAMP = "slot_assignment_timestamp"

    # Processing phase metadata
    PHASE_INITIATED_AT = "phase_initiated_at"
    PHASE_COMPLETED_AT = "phase_completed_at"
    PROCESSING_ATTEMPT_COUNT = "processing_attempt_count"
    LAST_ERROR_MESSAGE = "last_error_message"

    # Service interaction metadata
    SPELLCHECK_SERVICE_REQUEST_ID = "spellcheck_service_request_id"
    CJ_ASSESSMENT_SERVICE_REQUEST_ID = "cj_assessment_service_request_id"
    NLP_SERVICE_REQUEST_ID = "nlp_service_request_id"
    AI_FEEDBACK_SERVICE_REQUEST_ID = "ai_feedback_service_request_id"


# Default values for essay creation
class EssayDefaults:
    """Default values used in essay creation and processing."""

    ENTITY_TYPE = "essay"
    INITIAL_PROCESSING_ATTEMPT_COUNT = 1
    MAX_PROCESSING_RETRIES = 3

    # Default metadata for new essays
    DEFAULT_PROCESSING_METADATA = {
        MetadataKey.ENTITY_TYPE: ENTITY_TYPE,
        MetadataKey.PROCESSING_ATTEMPT_COUNT: INITIAL_PROCESSING_ATTEMPT_COUNT,
    }


# Service result handling constants
class ServiceResultStatus:
    """Constants for service result processing."""

    SUCCESS = "success"
    FAILED = "failed"
    RETRY_NEEDED = "retry_needed"
    PERMANENTLY_FAILED = "permanently_failed"


# Batch coordination constants
class BatchCoordination:
    """Constants for batch-level coordination operations."""

    # Batch completion thresholds
    MIN_SUCCESS_RATE_FOR_COMPLETION = 0.8  # 80% success rate required
    MAX_FAILURE_RATE_FOR_CONTINUATION = 0.2  # Stop if >20% fail

    # Timeout constants (in seconds)
    BATCH_PHASE_COMPLETION_TIMEOUT = 3600  # 1 hour
    INDIVIDUAL_ESSAY_PROCESSING_TIMEOUT = 300  # 5 minutes

    # Retry configuration
    MAX_BATCH_RETRY_ATTEMPTS = 3
    RETRY_BACKOFF_SECONDS = 60  # Initial backoff
    RETRY_BACKOFF_MULTIPLIER = 2  # Exponential backoff


# Query operation constants
class QueryLimits:
    """Constants for query operations and pagination."""

    DEFAULT_BATCH_ESSAY_LIMIT = 1000  # Max essays per batch query
    MAX_PHASE_QUERY_RESULTS = 5000  # Max results for phase queries
    DEFAULT_PAGE_SIZE = 50  # Default pagination size
    MAX_PAGE_SIZE = 200  # Maximum allowed page size
