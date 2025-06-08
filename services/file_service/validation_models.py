"""
Validation models for File Service content validation.

This module defines Pydantic models used for representing validation
results and error states in the File Service validation framework.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ValidationResult(BaseModel):
    """
    Result of content validation with error details.

    This model represents the outcome of file content validation,
    including success/failure status and detailed error information
    for providing actionable feedback to users.
    """

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    is_valid: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    warnings: List[str] = []
