"""
Text processing utilities for File Service.

This module provides basic text extraction and student information parsing
functionality for the walking skeleton implementation.
"""

from __future__ import annotations

from uuid import UUID

from huleedu_service_libs.error_handling.file_validation_factories import (
    raise_text_extraction_failed,
)
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("file_service.text_processing")


async def extract_text_from_file(file_content: bytes, file_name: str, correlation_id: UUID) -> str:
    """
    Extract text content from file bytes.

    For the walking skeleton, this provides basic .txt file extraction.
    Non-txt files are handled by raising an extraction error.

    Args:
        file_content: Raw file bytes
        file_name: Original filename for type detection
        correlation_id: Request correlation ID for tracing

    Returns:
        Extracted text content as string

    Raises:
        HuleEduError: If extraction fails
    """
    if not file_name.lower().endswith(".txt"):
        logger.warning(
            f"Non-txt file received: {file_name}. Walking skeleton only supports .txt files.",
        )
        raise_text_extraction_failed(
            service="file_service",
            operation="extract_text_from_file",
            file_name=file_name,
            message="Unsupported file type. Walking skeleton only supports .txt files",
            correlation_id=correlation_id,
        )

    try:
        # Basic text extraction for .txt files
        text = file_content.decode("utf-8", errors="ignore")
        logger.info(f"Successfully extracted {len(text)} characters from {file_name}")
        return text
    except Exception as e:
        logger.error(f"Error extracting text from {file_name}: {e}", exc_info=True)
        raise_text_extraction_failed(
            service="file_service",
            operation="extract_text_from_file",
            file_name=file_name,
            message=f"Failed to decode file content: {str(e)}",
            correlation_id=correlation_id,
            error_details=str(e),
        )


async def parse_student_info(text_content: str) -> tuple[str | None, str | None]:
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
