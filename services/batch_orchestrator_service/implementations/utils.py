"""Utility helpers for Batch Orchestrator Service implementations.

Currently contains language-related helpers used by multiple initiator
implementations. Keep this module minimal and free of dependencies on the
individual initiators to avoid circular imports.
"""

from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger

from common_core.domain_enums import CourseCode, Language, get_course_language

logger = create_service_logger("bos.language_utils")


def _infer_language_from_course_code(course_code: CourseCode) -> Language:
    """Infer ISO language code from a CourseCode enum member.

    Args:
        course_code: Course code enum member (e.g. CourseCode.SV1, CourseCode.ENG5).

    Returns:
        A Language enum member (e.g. Language.SWEDISH or Language.ENGLISH).
    """
    return get_course_language(course_code)
