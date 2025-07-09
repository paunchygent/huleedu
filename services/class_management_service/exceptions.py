"""Custom exception classes for Class Management Service."""

from __future__ import annotations

from common_core.domain_enums import CourseCode
from common_core.error_enums import ClassManagementErrorCode


class ClassManagementServiceError(Exception):
    """Base exception for Class Management Service errors."""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class CourseValidationError(ClassManagementServiceError):
    """Raised when course validation fails."""

    def __init__(self, message: str, invalid_course_codes: list[CourseCode] | None = None) -> None:
        super().__init__(message, ClassManagementErrorCode.COURSE_VALIDATION_ERROR.value)
        self.invalid_course_codes = invalid_course_codes or []


class CourseNotFoundError(ClassManagementServiceError):
    """Raised when requested course codes are not found in the database."""

    def __init__(self, missing_course_codes: list[CourseCode]) -> None:
        course_codes_str = ", ".join(code.value for code in missing_course_codes)
        message = f"Course codes not found: {course_codes_str}"
        super().__init__(message, ClassManagementErrorCode.COURSE_NOT_FOUND.value)
        self.missing_course_codes = missing_course_codes


class MultipleCourseError(ClassManagementServiceError):
    """Raised when multiple courses are provided but only one is supported."""

    def __init__(self, provided_course_codes: list[CourseCode]) -> None:
        course_codes_str = ", ".join(code.value for code in provided_course_codes)
        message = f"Multiple courses provided ({course_codes_str}), but only one course per class is supported"
        super().__init__(message, ClassManagementErrorCode.MULTIPLE_COURSE_ERROR.value)
        self.provided_course_codes = provided_course_codes


class ClassNotFoundError(ClassManagementServiceError):
    """Raised when a class is not found."""

    def __init__(self, class_id: str) -> None:
        message = f"Class not found: {class_id}"
        super().__init__(message, ClassManagementErrorCode.CLASS_NOT_FOUND.value)
        self.class_id = class_id


class StudentNotFoundError(ClassManagementServiceError):
    """Raised when a student is not found."""

    def __init__(self, student_id: str) -> None:
        message = f"Student not found: {student_id}"
        super().__init__(message, ClassManagementErrorCode.STUDENT_NOT_FOUND.value)
        self.student_id = student_id
