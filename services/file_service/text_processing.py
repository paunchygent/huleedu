"""
Text processing utilities for File Service.

This module provides basic text extraction and student information parsing
functionality for the walking skeleton implementation.
"""

from __future__ import annotations

from typing import Optional, Tuple

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("file_service.text_processing")


async def extract_text_from_file(file_content: bytes, file_name: str) -> str:
    """
    Extract text content from file bytes.

    For the walking skeleton, this provides basic .txt file extraction.
    Non-txt files are handled by logging a warning and returning empty string.

    Args:
        file_content: Raw file bytes
        file_name: Original filename for type detection

    Returns:
        Extracted text content as string
    """
    if not file_name.lower().endswith(".txt"):
        logger.warning(
            f"Non-txt file received: {file_name}. Walking skeleton only supports .txt files."
        )
        return ""

    try:
        # Basic text extraction for .txt files
        text = file_content.decode("utf-8", errors="ignore")
        logger.info(f"Successfully extracted {len(text)} characters from {file_name}")
        return text
    except Exception as e:
        logger.error(f"Error extracting text from {file_name}: {e}", exc_info=True)
        return ""


async def parse_student_info(text_content: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse student name and email from text content.

    STUB IMPLEMENTATION for walking skeleton.
    Always returns None, None as specified in task requirements.

    Args:
        text_content: Essay text content

    Returns:
        Tuple of (student_name, student_email) - both None in walking skeleton
    """
    logger.info("Student info parsing stub called. Returning None, None.")
    # TODO: Implement actual student name/email parsing from text_content
    # (e.g., using regex) in a future phase.
    return None, None
