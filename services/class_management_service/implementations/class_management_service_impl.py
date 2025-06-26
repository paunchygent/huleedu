
from __future__ import annotations

import uuid
from typing import Generic, Type

from common_core.events.class_events import ClassCreatedV1, StudentCreatedV1
from common_core.events.envelope import EventEnvelope
from services.class_management_service.api_models import (
    CreateClassRequest,
    CreateStudentRequest,
)
from services.class_management_service.models_db import Student, UserClass

# Import the type variables from protocols to ensure they match
from services.class_management_service.protocols import (
    ClassEventPublisherProtocol,
    ClassManagementServiceProtocol,
    ClassRepositoryProtocol,
    T,
    U,
)


class ClassManagementServiceImpl(ClassManagementServiceProtocol, Generic[T, U]):
    """Implementation of the class management service logic."""

    def __init__(
        self,
        repo: ClassRepositoryProtocol[T, U],  # Repository that returns T and U
        event_publisher: ClassEventPublisherProtocol,
        user_class_type: Type[T],
        student_type: Type[U]
    ) -> None:
        self.repo = repo
        self.event_publisher = event_publisher
        self._user_class_type = user_class_type
        self._student_type = student_type
        # Verify at runtime that the types match
        if not issubclass(user_class_type, UserClass):
            raise TypeError(f"user_class_type must be a subclass of UserClass, got {user_class_type.__name__}")
        if not issubclass(student_type, Student):
            raise TypeError(f"student_type must be a subclass of Student, got {student_type.__name__}")

    async def register_new_class(
        self, user_id: str, request: CreateClassRequest, correlation_id: uuid.UUID
    ) -> T:  # Returns type T (UserClass or subclass)
        # The type checker knows that create_class returns T
        new_class: T = await self.repo.create_class(user_id, request)

        # Access attributes that are guaranteed by the UserClass base class
        event_data = ClassCreatedV1(
            class_id=str(new_class.id),
            class_designation=new_class.name,
            course_codes=[new_class.course.course_code],  # Convert to list of CourseCode
            user_id=user_id,
        )
        envelope = EventEnvelope[ClassCreatedV1](
            event_type="huleedu.class.created.v1",
            source_service="class_management_service",
            correlation_id=correlation_id,
            data=event_data,
        )
        await self.event_publisher.publish_class_event(envelope)

        return new_class  # Type is preserved as T

    async def add_student_to_class(
        self, user_id: str, request: CreateStudentRequest, correlation_id: uuid.UUID
    ) -> U:  # Returns type U (Student or subclass)
        # The type checker knows that create_student returns U
        new_student: U = await self.repo.create_student(user_id, request)

        # Access attributes that are guaranteed by the Student base class
        event_data = StudentCreatedV1(
            student_id=str(new_student.id),
            first_name=new_student.first_name,
            last_name=new_student.last_name,
            student_email=new_student.email,
            class_ids=[str(c.id) for c in new_student.classes],
            created_by_user_id=user_id,
        )
        envelope = EventEnvelope[StudentCreatedV1](
            event_type="huleedu.student.created.v1",
            source_service="class_management_service",
            correlation_id=correlation_id,
            data=event_data,
        )
        await self.event_publisher.publish_class_event(envelope)

        return new_student  # Type is preserved as U
