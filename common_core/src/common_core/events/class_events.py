"""
Class management event models for student and class operations.

These events support class creation, student management, and essay-student
associations following the thin event principle.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from ..domain_enums import CourseCode


class ClassCreatedV1(BaseModel):
    """Event published when new class is created."""

    event: str = Field(default="class.created")
    class_id: str = Field(description="New class identifier")
    class_designation: str = Field(description="Class designation name")
    course_codes: list[CourseCode] = Field(description="Associated course codes")
    user_id: str = Field(description="Teacher who created the class")
    correlation_id: UUID | None = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StudentCreatedV1(BaseModel):
    """Event published when new student is created."""

    event: str = Field(default="student.created")
    student_id: str = Field(description="New student identifier")
    first_name: str = Field(description="Student first name")
    last_name: str = Field(description="Student last name")
    student_email: str | None = Field(description="Student email address")
    class_ids: list[str] = Field(description="Associated class identifiers")
    created_by_user_id: str = Field(description="User who created the student")
    correlation_id: UUID | None = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ClassUpdatedV1(BaseModel):
    """Event published when an existing class is updated."""

    event: str = Field(default="class.updated")
    class_id: str = Field(description="Updated class identifier")
    class_designation: str | None = Field(None, description="Updated class designation name")
    course_codes: list[CourseCode] | None = Field(None, description="Updated associated course codes")
    user_id: str = Field(description="Teacher who owns the class")
    correlation_id: UUID | None = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StudentUpdatedV1(BaseModel):
    """Event published when an existing student is updated."""

    event: str = Field(default="student.updated")
    student_id: str = Field(description="Updated student identifier")
    first_name: str | None = Field(None, description="Updated student first name")
    last_name: str | None = Field(None, description="Updated student last name")
    student_email: str | None = Field(None, description="Updated student email address")
    add_class_ids: list[str] | None = Field(None, description="Class IDs added to student")
    remove_class_ids: list[str] | None = Field(None, description="Class IDs removed from student")
    updated_by_user_id: str = Field(description="User who updated the student")
    correlation_id: UUID | None = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EssayStudentAssociationUpdatedV1(BaseModel):
    """Event published when student-essay association is created/updated."""

    event: str = Field(default="essay.student.association.updated")
    batch_id: str = Field(description="Batch identifier")
    essay_id: str = Field(description="Essay identifier")
    student_id: str | None = Field(description="Student identifier (None if association removed)")
    first_name: str | None = Field(description="Student first name for display")
    last_name: str | None = Field(description="Student last name for display")
    student_email: str | None = Field(description="Student email for display")
    association_method: str = Field(description="Association method: 'parsed' or 'manual'")
    confidence_score: float | None = Field(description="Confidence score for parsed associations")
    created_by_user_id: str = Field(description="User who created the association")
    correlation_id: UUID | None = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
