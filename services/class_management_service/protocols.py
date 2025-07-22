from __future__ import annotations

import uuid
from typing import Generic, Protocol, TypeVar
from uuid import UUID

from common_core.events.envelope import EventEnvelope

from services.class_management_service.api_models import (
    CreateClassRequest,
    CreateStudentRequest,
    UpdateClassRequest,
    UpdateStudentRequest,
)
from services.class_management_service.models_db import Student, UserClass

T = TypeVar("T", bound=UserClass, covariant=True)  # For UserClass types
U = TypeVar("U", bound=Student, covariant=True)  # For Student types


class ClassRepositoryProtocol(Protocol, Generic[T, U]):
    """Protocol for class and student data persistence operations."""

    async def create_class(
        self, user_id: str, class_data: CreateClassRequest, correlation_id: UUID
    ) -> T:  # Returns type T (UserClass or subclass)
        ...

    async def get_class_by_id(self, class_id: uuid.UUID) -> T | None:  # Returns type T or None
        ...

    async def update_class(
        self, class_id: uuid.UUID, class_data: UpdateClassRequest, correlation_id: UUID
    ) -> T | None:  # Returns type T or None
        ...

    async def delete_class(self, class_id: uuid.UUID) -> bool: ...

    async def create_student(
        self, user_id: str, student_data: CreateStudentRequest, correlation_id: UUID
    ) -> U:  # Returns type U (Student or subclass)
        ...

    async def get_student_by_id(self, student_id: uuid.UUID) -> U | None:  # Returns type U or None
        ...

    async def update_student(
        self, student_id: uuid.UUID, student_data: UpdateStudentRequest, correlation_id: UUID
    ) -> U | None:  # Returns type U or None
        ...

    async def delete_student(self, student_id: uuid.UUID) -> bool: ...

    async def associate_essay_to_student(
        self, user_id: str, essay_id: uuid.UUID, student_id: uuid.UUID, correlation_id: UUID
    ) -> None: ...


class ClassEventPublisherProtocol(Protocol):
    """Protocol for publishing class management-related events."""

    async def publish_class_event(self, event_envelope: EventEnvelope) -> None:
        """Publish a class management event to the appropriate Kafka topic."""
        ...


class ClassManagementServiceProtocol(Protocol, Generic[T, U]):
    """Protocol for the core business logic of the Class Management Service."""

    async def register_new_class(
        self, user_id: str, request: CreateClassRequest, correlation_id: uuid.UUID
    ) -> T:  # Returns type T (UserClass or subclass)
        ...

    async def get_class_by_id(self, class_id: uuid.UUID) -> T | None:
        """Retrieve a class by its ID."""
        ...

    async def update_class(
        self,
        user_id: str,
        class_id: uuid.UUID,
        request: UpdateClassRequest,
        correlation_id: uuid.UUID,
    ) -> T | None:
        """Update an existing class."""
        ...

    async def delete_class(self, class_id: uuid.UUID) -> bool:
        """Delete a class by its ID."""
        ...

    async def add_student_to_class(
        self, user_id: str, request: CreateStudentRequest, correlation_id: uuid.UUID
    ) -> U:  # Returns type U (Student or subclass)
        ...

    async def get_student_by_id(self, student_id: uuid.UUID) -> U | None:
        """Retrieve a student by their ID."""
        ...

    async def update_student(
        self,
        user_id: str,
        student_id: uuid.UUID,
        request: UpdateStudentRequest,
        correlation_id: uuid.UUID,
    ) -> U | None:
        """Update an existing student."""
        ...

    async def delete_student(self, student_id: uuid.UUID) -> bool:
        """Delete a student by their ID."""
        ...
