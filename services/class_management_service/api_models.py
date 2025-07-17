from __future__ import annotations

import uuid

from common_core.domain_enums import CourseCode
from common_core.metadata_models import ParsedNameMetadata, PersonNameV1
from pydantic import BaseModel, EmailStr, Field

# ====================================================================
# Request Models
# ====================================================================


class CreateClassRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    course_codes: list[CourseCode] = Field(
        ..., min_length=1, description="At least one course code is required"
    )


class UpdateClassRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    course_codes: list[CourseCode] | None = Field(
        None, min_length=1, description="At least one course code is required if provided"
    )


class CreateStudentRequest(BaseModel):
    person_name: PersonNameV1
    email: EmailStr | None = None
    class_ids: list[uuid.UUID] | None = None


class UpdateStudentRequest(BaseModel):
    person_name: PersonNameV1 | None = None
    email: EmailStr | None = None
    add_class_ids: list[uuid.UUID] | None = None
    remove_class_ids: list[uuid.UUID] | None = None


class EssayStudentAssociationRequest(BaseModel):
    essay_id: uuid.UUID
    student_id: uuid.UUID


# ====================================================================
# Response Models
# ====================================================================


class StudentResponse(BaseModel):
    id: uuid.UUID
    person_name: PersonNameV1
    email: EmailStr | None
    class_ids: list[uuid.UUID]


class ClassResponse(BaseModel):
    id: uuid.UUID
    name: str
    course_code: CourseCode
    student_count: int
    students: list[StudentResponse]


class EssayStudentAssociationResponse(BaseModel):
    id: uuid.UUID
    essay_id: uuid.UUID
    student_id: uuid.UUID


# ====================================================================
# Parsing Models
# ====================================================================


class StudentParsingResult(BaseModel):
    parsed_name: ParsedNameMetadata
    confidence: float = Field(..., ge=0.0, le=1.0)
