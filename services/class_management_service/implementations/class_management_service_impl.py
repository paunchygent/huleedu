from __future__ import annotations

import uuid
from typing import Any, Generic, Type

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.class_events import (
    ClassCreatedV1,
    ClassUpdatedV1,
    StudentCreatedV1,
    StudentUpdatedV1,
)
from common_core.events.envelope import EventEnvelope

from services.class_management_service.api_models import (
    CreateClassRequest,
    CreateStudentRequest,
    UpdateClassRequest,
    UpdateStudentRequest,
)
from services.class_management_service.constants import PHASE1_CONFIDENCE_SCORE, UNKNOWN_USER
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
        student_type: Type[U],
    ) -> None:
        self.repo = repo
        self.event_publisher = event_publisher
        self._user_class_type = user_class_type
        self._student_type = student_type
        # Verify at runtime that the types match
        if not issubclass(user_class_type, UserClass):
            raise TypeError(
                f"user_class_type must be a subclass of UserClass, got {user_class_type.__name__}"
            )
        if not issubclass(student_type, Student):
            raise TypeError(
                f"student_type must be a subclass of Student, got {student_type.__name__}"
            )

    async def register_new_class(
        self, user_id: str, request: CreateClassRequest, correlation_id: uuid.UUID
    ) -> T:  # Returns type T (UserClass or subclass)
        # The type checker knows that create_class returns T
        new_class: T = await self.repo.create_class(user_id, request, correlation_id)

        # Access attributes that are guaranteed by the UserClass base class
        event_data = ClassCreatedV1(
            class_id=str(new_class.id),
            class_designation=new_class.name,
            course_codes=[new_class.course.course_code],  # Convert to list of CourseCode
            user_id=user_id,
        )
        envelope = EventEnvelope[ClassCreatedV1](
            event_type=topic_name(ProcessingEvent.CLASS_CREATED),
            source_service="class_management_service",
            correlation_id=correlation_id,
            data=event_data,
        )
        await self.event_publisher.publish_class_event(envelope)

        return new_class  # Type is preserved as T

    async def get_class_by_id(self, class_id: uuid.UUID) -> T | None:
        """Retrieve a class by its ID."""
        return await self.repo.get_class_by_id(class_id)

    async def update_class(
        self,
        user_id: str,
        class_id: uuid.UUID,
        request: UpdateClassRequest,
        correlation_id: uuid.UUID,
    ) -> T | None:
        updated_class = await self.repo.update_class(class_id, request, correlation_id)
        if updated_class:
            event_data = ClassUpdatedV1(
                class_id=str(updated_class.id),
                class_designation=updated_class.name,
                course_codes=[updated_class.course.course_code] if updated_class.course else None,
                user_id=user_id,
                correlation_id=correlation_id,
            )
            envelope = EventEnvelope[ClassUpdatedV1](
                event_type=topic_name(ProcessingEvent.CLASS_UPDATED),
                source_service="class_management_service",
                correlation_id=correlation_id,
                data=event_data,
            )
            await self.event_publisher.publish_class_event(envelope)
        return updated_class

    async def delete_class(self, class_id: uuid.UUID) -> bool:
        """Delete a class by its ID."""
        return await self.repo.delete_class(class_id)

    async def add_student_to_class(
        self, user_id: str, request: CreateStudentRequest, correlation_id: uuid.UUID
    ) -> U:  # Returns type U (Student or subclass)
        # The type checker knows that create_student returns U
        new_student: U = await self.repo.create_student(user_id, request, correlation_id)

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
            event_type=topic_name(ProcessingEvent.STUDENT_CREATED),
            source_service="class_management_service",
            correlation_id=correlation_id,
            data=event_data,
        )
        await self.event_publisher.publish_class_event(envelope)

        return new_student  # Type is preserved as U

    async def get_student_by_id(self, student_id: uuid.UUID) -> U | None:
        """Retrieve a student by their ID."""
        return await self.repo.get_student_by_id(student_id)

    async def update_student(
        self,
        user_id: str,
        student_id: uuid.UUID,
        request: UpdateStudentRequest,
        correlation_id: uuid.UUID,
    ) -> U | None:
        updated_student = await self.repo.update_student(student_id, request, correlation_id)
        if updated_student:
            add_class_ids = None
            if request.add_class_ids:
                add_class_ids = [str(c_id) for c_id in request.add_class_ids]

            remove_class_ids = None
            if request.remove_class_ids:
                remove_class_ids = [str(c_id) for c_id in request.remove_class_ids]

            event_data = StudentUpdatedV1(
                student_id=str(updated_student.id),
                first_name=updated_student.first_name,
                last_name=updated_student.last_name,
                student_email=updated_student.email,
                add_class_ids=add_class_ids,
                remove_class_ids=remove_class_ids,
                updated_by_user_id=user_id,
                correlation_id=correlation_id,
            )
            envelope = EventEnvelope[StudentUpdatedV1](
                event_type=topic_name(ProcessingEvent.STUDENT_UPDATED),
                source_service="class_management_service",
                correlation_id=correlation_id,
                data=event_data,
            )
            await self.event_publisher.publish_class_event(envelope)
        return updated_student

    async def delete_student(self, student_id: uuid.UUID) -> bool:
        """Delete a student by their ID."""
        return await self.repo.delete_student(student_id)

    async def get_batch_student_associations(self, batch_id: uuid.UUID) -> list[dict[str, Any]]:
        """Retrieve student-essay association suggestions for teacher validation."""
        # Query associations from repository
        associations = await self.repo.get_batch_student_associations(batch_id)
        
        # Format associations for API response
        formatted_associations = []
        for assoc in associations:
            formatted_associations.append({
                "essay_id": str(assoc.essay_id),
                "suggested_student_id": str(assoc.student_id),
                "confidence_score": PHASE1_CONFIDENCE_SCORE,
                "match_reasons": ["Name extracted from essay header"],
                "created_at": assoc.created_at.isoformat()
            })
        
        return formatted_associations

    async def confirm_batch_student_associations(
        self, batch_id: uuid.UUID, confirmations: dict[str, Any], correlation_id: uuid.UUID
    ) -> dict[str, Any]:
        """Process teacher confirmations and publish StudentAssociationsConfirmed event."""
        # Get class_id from the confirmations data or associations
        # The class_id should be provided in the confirmation request
        class_id = confirmations.get("class_id", str(uuid.uuid4()))
        
        # Process confirmations
        confirmed_associations = []
        validation_summary = {
            "total_associations": len(confirmations.get("associations", [])),
            "confirmed": 0,
            "rejected": 0
        }
        
        for assoc in confirmations.get("associations", []):
            if assoc.get("confirmed", False):
                confirmed_associations.append({
                    "essay_id": assoc["essay_id"],
                    "student_id": assoc["student_id"],
                    "confidence_score": PHASE1_CONFIDENCE_SCORE,
                    "validation_method": "human",  # Using literal from event model
                    "validated_by": confirmations.get("user_id", UNKNOWN_USER),  # Should be provided in request
                })
                validation_summary["confirmed"] += 1
            else:
                validation_summary["rejected"] += 1
        
        # Publish StudentAssociationsConfirmed event
        await self.event_publisher.publish_student_associations_confirmed(
            batch_id=str(batch_id),
            class_id=class_id,
            associations=confirmed_associations,
            timeout_triggered=False,
            validation_summary=validation_summary,
            correlation_id=correlation_id
        )
        
        return {
            "status": "confirmed",
            "associations_confirmed": validation_summary["confirmed"],
            "associations_rejected": validation_summary["rejected"]
        }
