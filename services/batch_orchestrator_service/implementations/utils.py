"""Utility helpers for Batch Orchestrator Service implementations.

Currently contains language-related helpers used by multiple initiator
implementations. Keep this module minimal and free of dependencies on the
individual initiators to avoid circular imports.
"""

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("bos.language_utils")


def _infer_language_from_course_code(course_code: str) -> str:  # noqa: D401
    """Infer ISO language code from a course code string.

    Args:
        course_code: Course code (e.g. "SV1", "ENG5").

    Returns:
        A two-letter language code (e.g. ``"sv"`` or ``"en"``).
    """
    course_code_upper = course_code.upper()

    if course_code_upper.startswith("SV"):
        return "sv"  # Swedish
    if course_code_upper.startswith("ENG"):
        return "en"  # English

    # Default to English if the course code is unrecognised
    logger.warning("Unknown course code '%s', defaulting to English", course_code)
    return "en"
