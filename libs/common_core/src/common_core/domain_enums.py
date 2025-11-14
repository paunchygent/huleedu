"""
common_core.domain_enums - Enums defining core business domain concepts.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Tuple


class ContentType(str, Enum):
    """Content type discriminators for StorageReferenceMetadata storage references.

    Defines content type categories for content stored in Content Service and
    referenced via StorageReferenceMetadata. Each type represents a distinct
    content artifact produced by a service during essay/batch processing.

    Storage Pattern:
    - Services store content in Content Service with ContentType discriminator
    - StorageReferenceMetadata.add_reference(content_type, storage_id, path)
      creates typed reference
    - Downstream services retrieve content using storage_id and validate
      content_type matches expected artifact

    Producer/Consumer relationships documented inline for each value.

    See: libs/common_core/docs/storage-references.md
    """

    ORIGINAL_ESSAY = (
        "original_essay"  # Producer: essay_lifecycle_service | Consumer: pipeline services
    )
    CORRECTED_TEXT = (
        "corrected_text"
        # Producer: spellchecker_service | Consumer: nlp_service, result_aggregator_service
    )
    PROCESSING_LOG = (
        "processing_log"  # Producer: multiple services | Consumer: observability/audit systems
    )
    NLP_METRICS_JSON = (
        "nlp_metrics_json"  # Producer: nlp_service | Consumer: result_aggregator_service, analytics
    )
    STUDENT_FACING_AI_FEEDBACK_TEXT = (
        "student_facing_ai_feedback_text"
        # Producer: llm_provider_service/ai_feedback | Consumer: result_aggregator_service
    )
    AI_EDITOR_REVISION_TEXT = (
        "ai_editor_revision_text"
        # Producer: llm_provider_service/ai_editor | Consumer: result_aggregator_service
    )
    AI_DETAILED_ANALYSIS_JSON = (
        "ai_detailed_analysis_json"
        # Producer: llm_provider_service/ai_analysis | Consumer: result_aggregator_service, analytics  # noqa: E501
    )
    GRAMMAR_ANALYSIS_JSON = (
        "grammar_analysis_json"
        # Producer: nlp_service (LanguageTool integration) | Consumer: result_aggregator_service
    )
    CJ_RESULTS_JSON = (
        "cj_results_json"
        # Producer: cj_assessment_service | Consumer: result_aggregator_service, analytics
    )
    RAW_UPLOAD_BLOB = (
        "raw_upload_blob"  # Producer: file_service | Consumer: reprocessing/audit workflows
    )
    EXTRACTED_PLAINTEXT = (
        "extracted_plaintext"
        # Producer: file_service | Consumer: spellchecker_service, nlp_service
    )
    STUDENT_PROMPT_TEXT = (
        "student_prompt_text"
        # Producer: batch_orchestrator_service (teacher upload) | Consumer: cj_assessment_service, nlp_service  # noqa: E501
    )


class CourseCode(str, Enum):
    """Predefined course codes for HuleEdu platform."""

    ENG5 = "ENG5"
    ENG6 = "ENG6"
    ENG7 = "ENG7"
    SV1 = "SV1"
    SV2 = "SV2"
    SV3 = "SV3"


class Language(str, Enum):
    """Supported languages inferred from course codes."""

    ENGLISH = "en"
    SWEDISH = "sv"


# --- Course Helpers ---
COURSE_METADATA: Dict[CourseCode, Tuple[str, Language, int]] = {
    CourseCode.ENG5: ("English 5", Language.ENGLISH, 5),
    CourseCode.ENG6: ("English 6", Language.ENGLISH, 6),
    CourseCode.ENG7: ("English 7", Language.ENGLISH, 7),
    CourseCode.SV1: ("Svenska 1", Language.SWEDISH, 1),
    CourseCode.SV2: ("Svenska 2", Language.SWEDISH, 2),
    CourseCode.SV3: ("Svenska 3", Language.SWEDISH, 3),
}


def get_course_language(course_code: CourseCode) -> Language:
    """Get language for a course code."""
    return COURSE_METADATA[course_code][1]


def get_course_name(course_code: CourseCode) -> str:
    """Get display name for a course code."""
    return COURSE_METADATA[course_code][0]


def get_course_level(course_code: CourseCode) -> int:
    """Get skill level for a course code."""
    return COURSE_METADATA[course_code][2]


class EssayComparisonWinner(str, Enum):
    """Essay comparison result values using assessment domain language."""

    ESSAY_A = "Essay A"
    ESSAY_B = "Essay B"
    ERROR = "Error"
