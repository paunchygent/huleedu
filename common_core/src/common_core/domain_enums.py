"""
common_core.domain_enums - Enums defining core business domain concepts.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Tuple


class ContentType(str, Enum):
    ORIGINAL_ESSAY = "original_essay"
    CORRECTED_TEXT = "corrected_text"  # spell_checker_service output
    PROCESSING_LOG = "processing_log"
    NLP_METRICS_JSON = "nlp_metrics_json"
    STUDENT_FACING_AI_FEEDBACK_TEXT = "student_facing_ai_feedback_text"
    AI_EDITOR_REVISION_TEXT = "ai_editor_revision_text"
    AI_DETAILED_ANALYSIS_JSON = "ai_detailed_analysis_json"
    GRAMMAR_ANALYSIS_JSON = "grammar_analysis_json"
    CJ_RESULTS_JSON = "cj_results_json"  # cj_assessment_service output
    RAW_UPLOAD_BLOB = "raw_upload_blob"
    EXTRACTED_PLAINTEXT = "extracted_plaintext"  # file_service output


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
