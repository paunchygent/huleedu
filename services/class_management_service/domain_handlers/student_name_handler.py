from __future__ import annotations

from typing import Any
from uuid import UUID

from common_core.metadata_models import PersonNameV1
from huleedu_service_libs.error_handling import raise_processing_error, raise_validation_error

from services.class_management_service.protocols import ClassRepositoryProtocol


class BatchStudentNameItem:
    """Single item in batch student name response."""

    def __init__(self, essay_id: UUID, student_id: UUID, student_person_name: PersonNameV1):
        self.essay_id = essay_id
        self.student_id = student_id
        self.student_person_name = student_person_name

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "essay_id": str(self.essay_id),
            "student_id": str(self.student_id),
            "student_person_name": {
                "first_name": self.student_person_name.first_name,
                "last_name": self.student_person_name.last_name,
                "legal_full_name": self.student_person_name.legal_full_name,
            },
        }


class BatchStudentNamesResponse:
    """Response model for batch student names endpoint."""

    def __init__(self, items: list[BatchStudentNameItem]):
        self.items = items

    def to_dict(self) -> list[dict[str, Any]]:
        """Convert to list of dictionaries for API responses."""
        return [item.to_dict() for item in self.items]


class EssayStudentAssociationResponse:
    """Response model for single essay student association endpoint."""

    def __init__(self, essay_id: UUID, student_id: UUID, student_person_name: PersonNameV1):
        self.essay_id = essay_id
        self.student_id = student_id
        self.student_person_name = student_person_name

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "essay_id": str(self.essay_id),
            "student_id": str(self.student_id),
            "student_person_name": {
                "first_name": self.student_person_name.first_name,
                "last_name": self.student_person_name.last_name,
                "legal_full_name": self.student_person_name.legal_full_name,
            },
        }


class StudentNameHandler:
    """Encapsulates student name resolution business logic for Phase 3 implementation."""

    def __init__(self, repository: ClassRepositoryProtocol):
        self._repository = repository

    async def get_batch_student_names(
        self, batch_id: str, correlation_id: UUID
    ) -> BatchStudentNamesResponse:
        """Get all student names for essays in a batch.

        Args:
            batch_id: The batch's ID as string
            correlation_id: Request correlation ID for observability

        Returns:
            BatchStudentNamesResponse with list of essay->student mappings

        Raises:
            HuleEduError: If validation fails or database error
        """
        try:
            batch_uuid = UUID(batch_id)
        except ValueError:
            raise_validation_error(
                service="class_management_service",
                operation="get_batch_student_names",
                field="batch_id",
                message="Invalid batch_id format",
                correlation_id=correlation_id,
            )

        try:
            name_mappings = await self._repository.get_batch_student_names(
                batch_uuid, correlation_id
            )

            items = []
            for mapping in name_mappings:
                items.append(
                    BatchStudentNameItem(
                        essay_id=mapping["essay_id"],
                        student_id=mapping["student_id"],
                        student_person_name=mapping["student_person_name"],
                    )
                )

            return BatchStudentNamesResponse(items=items)

        except Exception as e:
            # Repository should handle specific errors; this catches unexpected issues
            raise_processing_error(
                service="class_management_service",
                operation="get_batch_student_names",
                message=f"Failed to retrieve batch student names: {str(e)}",
                correlation_id=correlation_id,
            )

    async def get_essay_student_association(
        self, essay_id: str, correlation_id: UUID
    ) -> EssayStudentAssociationResponse | None:
        """Get student association for a single essay.

        Args:
            essay_id: The essay's ID as string
            correlation_id: Request correlation ID for observability

        Returns:
            EssayStudentAssociationResponse if association exists, None otherwise

        Raises:
            HuleEduError: If validation fails or database error
        """
        try:
            essay_uuid = UUID(essay_id)
        except ValueError:
            raise_validation_error(
                service="class_management_service",
                operation="get_essay_student_association",
                field="essay_id",
                message="Invalid essay_id format",
                correlation_id=correlation_id,
            )

        try:
            association = await self._repository.get_essay_student_association(
                essay_uuid, correlation_id
            )

            if not association:
                return None

            return EssayStudentAssociationResponse(
                essay_id=association["essay_id"],
                student_id=association["student_id"],
                student_person_name=association["student_person_name"],
            )

        except Exception as e:
            # Repository should handle specific errors; this catches unexpected issues
            raise_processing_error(
                service="class_management_service",
                operation="get_essay_student_association",
                message=f"Failed to retrieve essay student association: {str(e)}",
                correlation_id=correlation_id,
            )
