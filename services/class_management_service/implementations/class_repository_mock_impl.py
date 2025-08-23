from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any, Type, TypeVar, cast
from uuid import UUID

from common_core.domain_enums import Language

from services.class_management_service.api_models import (
    CreateClassRequest,
    CreateStudentRequest,
    UpdateClassRequest,
    UpdateStudentRequest,
)
from services.class_management_service.models_db import Course, Student, UserClass
from services.class_management_service.protocols import (
    ClassRepositoryProtocol,
)

# Define concrete types for this implementation
T = TypeVar("T", bound=UserClass)  # T must be UserClass or a subclass
U = TypeVar("U", bound=Student)  # U must be Student or a subclass


class MockClassRepositoryImpl(ClassRepositoryProtocol[T, U]):
    """Mock implementation of ClassRepositoryProtocol for testing with generic types."""

    def __init__(self) -> None:
        self._user_class_type: Type[T] = cast(Type[T], UserClass)
        self._student_type: Type[U] = cast(Type[U], Student)
        self.classes: dict[uuid.UUID, T] = {}
        self.students: dict[uuid.UUID, U] = {}
        self.associations: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)

    async def create_class(
        self, user_id: str, class_data: CreateClassRequest, correlation_id: UUID
    ) -> T:  # Returns type T (UserClass or subclass)
        class_id = uuid.uuid4()
        # This is a simplified mock, we just pick the first course code
        course = Course(
            id=uuid.uuid4(),
            course_code=class_data.course_codes[0],
            name="Mock Course",
            language=Language.ENGLISH,
        )
        new_class = UserClass(
            id=class_id,
            name=class_data.name,
            created_by_user_id=user_id,
            course_id=course.id,
            course=course,
            students=[],
        )
        self.classes[class_id] = cast(T, new_class)
        return cast(T, new_class)

    async def get_class_by_id(self, class_id: uuid.UUID) -> T | None:  # Returns type T or None
        return cast(T | None, self.classes.get(class_id))

    async def update_class(
        self, class_id: uuid.UUID, class_data: UpdateClassRequest, correlation_id: UUID
    ) -> T | None:  # Returns type T or None
        if class_id not in self.classes:
            return None
        if class_data.name:
            self.classes[class_id].name = class_data.name
        # Mock doesn't handle course updates
        return cast(T | None, self.classes[class_id])

    async def delete_class(self, class_id: uuid.UUID) -> bool:
        if class_id in self.classes:
            del self.classes[class_id]
            return True
        return False

    async def create_student(
        self, user_id: str, student_data: CreateStudentRequest, correlation_id: UUID
    ) -> U:  # Returns type U (Student or subclass)
        student_id = uuid.uuid4()
        new_student = Student(
            id=student_id,
            first_name=student_data.person_name.first_name,
            last_name=student_data.person_name.last_name,
            legal_full_name=student_data.person_name.legal_full_name,
            email=student_data.email,
            created_by_user_id=user_id,
            classes=[],
        )
        self.students[student_id] = cast(U, new_student)
        if student_data.class_ids:
            for class_id in student_data.class_ids:
                if class_id in self.classes:
                    self.classes[class_id].students.append(new_student)
                    new_student.classes.append(self.classes[class_id])
        return cast(U, new_student)

    async def get_student_by_id(self, student_id: uuid.UUID) -> U | None:  # Returns type U or None
        return cast(U | None, self.students.get(student_id))

    async def update_student(
        self, student_id: uuid.UUID, student_data: UpdateStudentRequest, correlation_id: UUID
    ) -> U | None:  # Returns type U or None
        if student_id not in self.students:
            return None
        student = self.students[student_id]
        if student_data.person_name:
            student.first_name = student_data.person_name.first_name
            student.last_name = student_data.person_name.last_name
            student.legal_full_name = student_data.person_name.legal_full_name
        if student_data.email:
            student.email = student_data.email
        # Mock doesn't handle class associations updates
        return cast(U | None, student)

    async def delete_student(self, student_id: uuid.UUID) -> bool:
        if student_id in self.students:
            del self.students[student_id]
            # Also remove from any classes
            for class_obj in self.classes.values():
                class_obj.students = [s for s in class_obj.students if s.id != student_id]
            return True
        return False

    async def get_batch_student_associations(self, batch_id: UUID) -> list[Any]:
        """Get all student-essay associations for a batch."""
        # Mock implementation returns empty list for now
        # In a more complete mock, this would track associations by batch_id
        return []

    async def get_batch_student_names(
        self, batch_id: UUID, correlation_id: UUID
    ) -> list[dict[str, Any]]:
        """Get all student names for essays in a batch with PersonNameV1 structure.

        Mock implementation returns empty list for testing.
        """
        # Mock implementation returns empty list
        # In a more complete mock, this would return test data
        return []

    async def get_essay_student_association(
        self, essay_id: UUID, correlation_id: UUID
    ) -> dict[str, Any] | None:
        """Get student association for a single essay with PersonNameV1 structure.

        Mock implementation returns None for testing.
        """
        # Mock implementation returns None
        # In a more complete mock, this could return test data
        return None

    async def list_classes_by_owner(self, user_id: str, limit: int, offset: int) -> list[T]:
        """Return classes filtered by created_by_user_id in insertion order (mock)."""
        owned = [c for c in self.classes.values() if c.created_by_user_id == user_id]
        # Simulate ordering by created_at descending is not tracked; return slice only
        sliced = owned[offset : offset + limit]
        return cast(list[T], list(sliced))
