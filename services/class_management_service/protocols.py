from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar
from uuid import UUID

if TYPE_CHECKING:
    from opentelemetry.trace import Span

import aiohttp
from aiokafka import ConsumerRecord
from common_core.domain_enums import CourseCode
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

    async def get_batch_student_associations(self, batch_id: UUID) -> list[Any]:
        """Get all student-essay associations for a batch."""
        ...

    async def get_batch_student_names(
        self, batch_id: UUID, correlation_id: UUID
    ) -> list[dict[str, Any]]:
        """Get all student names for essays in a batch.

        Returns:
            List of dictionaries with keys: essay_id, student_id, student_person_name
        """
        ...

    async def get_essay_student_association(
        self, essay_id: UUID, correlation_id: UUID
    ) -> dict[str, Any] | None:
        """Get student association for a single essay.

        Returns:
            Dictionary with keys: essay_id, student_id, student_person_name, or None if not found
        """
        ...

    async def list_classes_by_owner(
        self, user_id: str, limit: int, offset: int
    ) -> list[T]:
        """List classes created by a specific user.

        Returns:
            A list of UserClass instances owned by the user.
        """
        ...


class ClassEventPublisherProtocol(Protocol):
    """Protocol for publishing class management-related events."""

    async def publish_class_event(self, event_envelope: EventEnvelope) -> None:
        """Publish a class management event to the appropriate Kafka topic."""
        ...

    async def publish_student_associations_confirmed(
        self,
        batch_id: str,
        class_id: str,
        course_code: CourseCode,
        associations: list[dict[str, Any]],
        timeout_triggered: bool,
        validation_summary: dict[str, int],
        correlation_id: UUID,
    ) -> None:
        """Publish StudentAssociationsConfirmedV1 event to ELS."""
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

    async def get_batch_student_associations(self, batch_id: UUID) -> list[dict[str, Any]]:
        """Retrieve student-essay association suggestions for teacher validation."""
        ...

    async def confirm_batch_student_associations(
        self, batch_id: UUID, confirmations: dict[str, Any], correlation_id: UUID
    ) -> dict[str, Any]:
        """Process teacher confirmations and publish StudentAssociationsConfirmed event."""
        ...

    async def list_classes_for_user(self, user_id: str, limit: int, offset: int) -> list[T]:
        """List classes for the given user (owner)."""
        ...


class CommandHandlerProtocol(Protocol):
    """Protocol for Kafka event command handlers."""

    async def can_handle(self, event_type: str) -> bool:
        """Check if this handler can process the given event type."""
        ...

    async def handle(
        self,
        msg: ConsumerRecord,
        envelope: EventEnvelope,
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
        span: "Span | None" = None,
    ) -> bool:
        """Handle the incoming event.

        Returns:
            True if processing succeeded, False otherwise
        """
        ...
