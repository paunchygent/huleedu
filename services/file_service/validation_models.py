"""
Validation models for File Service content validation.

This module defines Pydantic models used for representing validation
results and error states in the File Service validation framework.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class FileValidationStatus(str, Enum):
    """File validation status values for metrics collection."""

    SUCCESS = "success"
    RAW_STORAGE_FAILED = "raw_storage_failed"
    EXTRACTION_FAILED = "extraction_failed"
    CONTENT_VALIDATION_FAILED = "content_validation_failed"


class FileProcessingStatus(str, Enum):
    """File processing status values for result reporting."""

    PROCESSING_SUCCESS = "processing_success"
    RAW_STORAGE_FAILED = "raw_storage_failed"
    EXTRACTION_FAILED = "extraction_failed"
    CONTENT_VALIDATION_FAILED = "content_validation_failed"


class ValidationResult(BaseModel):
    """
    Result of content validation with error details.

    This model represents the outcome of file content validation,
    including success/failure status and detailed error information
    for providing actionable feedback to users.
    """

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    is_valid: bool
    error_code: str | None = None
    error_message: str | None = None
    warnings: list[str] = []
