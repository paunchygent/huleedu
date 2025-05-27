"""
Pydantic models for AI feedback processing events.

These models define the data structures for AI feedback processing inputs
and results as specified in the PRD.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

__all__ = [
    "AIFeedbackInputDataV1",
]


class AIFeedbackInputDataV1(BaseModel):
    """Input data structure for AI feedback processing requests."""

    text_storage_id: str
    course_code: str
    essay_instructions: str
    language: str
    teacher_name: Optional[str] = None
    class_designation: Optional[str] = None
    user_id_of_batch_owner: Optional[str] = None
    student_name: Optional[str] = None
