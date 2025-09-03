"""
Content idempotency and slot assignment operations for Essay Lifecycle Service.

Handles complex transactional operations for content provisioning
with atomic idempotency checks and race condition prevention.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus
from huleedu_service_libs.error_handling import raise_processing_error
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.essay_lifecycle_service.domain_models import EssayState as ConcreteEssayState
from services.essay_lifecycle_service.implementations.essay_repository_mappers import (
    EssayRepositoryMappers,
)
from services.essay_lifecycle_service.implementations.essay_repository_queries import (
    EssayRepositoryQueries,
)
from services.essay_lifecycle_service.models_db import EssayStateDB

if TYPE_CHECKING:
    pass

logger = create_service_logger("els.repository.idempotency")


class EssayIdempotencyOperations:
    """Complex idempotency operations for content provisioning and slot assignments."""

    def __init__(self) -> None:
        """Initialize idempotency operations."""
        self.mappers = EssayRepositoryMappers()
        self.queries = EssayRepositoryQueries()

    async def create_or_update_essay_state_for_slot_assignment(
        self,
        session: AsyncSession,
        internal_essay_id: str,
        batch_id: str,
        text_storage_id: str,
        original_file_name: str,
        file_size: int,
        content_hash: str | None,
        initial_status: EssayStatus,
        correlation_id: UUID | None = None,
    ) -> ConcreteEssayState:
        """Create or update essay state for slot assignment with content metadata."""
        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            from uuid import uuid4

            correlation_id = uuid4()

        try:
            # Check if essay already exists
            existing_essay = await self.queries.get_essay_state(session, internal_essay_id)

            if existing_essay is not None:
                # Update existing essay with new metadata
                metadata = {
                    "text_storage_id": text_storage_id,
                    "original_file_name": original_file_name,
                    "file_size": file_size,
                    "content_hash": content_hash,
                    "slot_assignment_timestamp": datetime.now(UTC).isoformat(),
                }

                existing_essay.processing_metadata.update(metadata)
                existing_essay.storage_references[ContentType.ORIGINAL_ESSAY] = text_storage_id
                existing_essay.current_status = initial_status
                existing_essay.batch_id = batch_id  # Ensure batch_id is set correctly
                existing_essay.updated_at = datetime.now(UTC)

                await self.queries.update_essay_state(
                    session,
                    internal_essay_id,
                    initial_status,
                    metadata,
                    correlation_id=correlation_id,
                )
                return existing_essay
            else:
                # Create new essay state
                essay_state = ConcreteEssayState(
                    essay_id=internal_essay_id,
                    batch_id=batch_id,
                    current_status=initial_status,
                    processing_metadata={
                        "text_storage_id": text_storage_id,
                        "original_file_name": original_file_name,
                        "file_size": file_size,
                        "content_hash": content_hash,
                        "slot_assignment_timestamp": datetime.now(UTC).isoformat(),
                    },
                    storage_references={ContentType.ORIGINAL_ESSAY: text_storage_id},
                    timeline={initial_status.value: datetime.now(UTC)},
                )

                db_data = self.mappers.essay_state_to_db_dict(essay_state)
                db_essay = EssayStateDB(**db_data)
                session.add(db_essay)

                logger.info(f"Created essay {internal_essay_id} for slot assignment")
                return essay_state

        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_processing_error(
                    service="essay_lifecycle_service",
                    operation="create_or_update_essay_state_for_slot_assignment",
                    message=f"Database error during slot assignment: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    essay_id=internal_essay_id,
                    batch_id=batch_id,
                    text_storage_id=text_storage_id,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def create_essay_state_with_content_idempotency(
        self,
        session: AsyncSession,
        batch_id: str,
        text_storage_id: str,
        essay_data: dict[str, Any],
        correlation_id: UUID,
    ) -> tuple[bool, str | None]:
        """
        Create essay state with atomic idempotency check for content provisioning.

        This method addresses ELS-002 Phase 1 requirements by providing database-level
        atomicity for content provisioning to prevent race conditions.

        Args:
            session: Database session for the transaction
            batch_id: The batch identifier
            text_storage_id: The content storage identifier
            essay_data: Dictionary containing essay creation data including internal_essay_id
            correlation_id: Correlation ID for distributed tracing

        Returns:
            tuple[bool, str | None]: (was_created, essay_id)
                - (True, essay_id) for new creation
                - (False, existing_essay_id) for idempotent case where content already assigned

        Raises:
            HuleEduError: For database errors or constraint violations
        """
        try:
            # Get internal essay ID
            internal_essay_id = essay_data["internal_essay_id"]
            initial_status = essay_data.get("initial_status", EssayStatus.READY_FOR_PROCESSING)

            # Check if essay already exists (created during batch registration)
            existing_stmt = select(EssayStateDB).where(EssayStateDB.essay_id == internal_essay_id)
            existing_result = await session.execute(existing_stmt)
            existing_essay_db = existing_result.scalars().first()

            if existing_essay_db:
                # Update existing essay with content information
                # CRITICAL: Always ensure batch_id is set - essays created during batch registration
                # already have batch_id, but we must preserve it. If somehow missing, set it now.
                if not existing_essay_db.batch_id:
                    existing_essay_db.batch_id = batch_id
                existing_essay_db.text_storage_id = text_storage_id
                existing_essay_db.current_status = initial_status.value  # type: ignore[assignment]
                existing_essay_db.processing_metadata = {
                    **existing_essay_db.processing_metadata,
                    "text_storage_id": text_storage_id,
                    "original_file_name": essay_data.get("original_file_name", ""),
                    "file_size": essay_data.get("file_size", 0),
                    "content_hash": essay_data.get("content_hash"),
                    "slot_assignment_timestamp": datetime.now(UTC).isoformat(),
                }
                existing_essay_db.storage_references = {
                    **existing_essay_db.storage_references,
                    ContentType.ORIGINAL_ESSAY.value: text_storage_id,
                }
                existing_essay_db.timeline = {
                    **existing_essay_db.timeline,
                    initial_status.value: datetime.now(UTC).isoformat(),
                }
                existing_essay_db.version += 1
            else:
                # Create new essay state (shouldn't happen in normal flow)
                essay_state = ConcreteEssayState(
                    essay_id=internal_essay_id,
                    batch_id=batch_id,
                    current_status=initial_status,
                    processing_metadata={
                        "text_storage_id": text_storage_id,
                        "original_file_name": essay_data.get("original_file_name", ""),
                        "file_size": essay_data.get("file_size", 0),
                        "content_hash": essay_data.get("content_hash"),
                        "slot_assignment_timestamp": datetime.now(UTC).isoformat(),
                    },
                    storage_references={ContentType.ORIGINAL_ESSAY: text_storage_id},
                    timeline={initial_status.value: datetime.now(UTC)},
                )

                # Convert to database format
                db_data = self.mappers.essay_state_to_db_dict(essay_state)
                # Explicitly set text_storage_id for the constraint
                db_data["text_storage_id"] = text_storage_id

                db_essay = EssayStateDB(**db_data)
                session.add(db_essay)

            # No commit here - let the handler manage the transaction

            logger.info(
                "Successfully created essay state with content assignment",
                extra={
                    "batch_id": batch_id,
                    "text_storage_id": text_storage_id,
                    "essay_id": internal_essay_id,
                    "correlation_id": str(correlation_id),
                },
            )
            return True, internal_essay_id

        except IntegrityError as e:
            # Handle unique constraint violation as idempotent success
            # Check for both our specific constraint name and general unique violation
            if (
                "uq_essay_content_idempotency_partial" in str(e)
                or "uq_essay_content_idempotency" in str(e)
                or (
                    "duplicate key" in str(e)
                    and "batch_id" in str(e)
                    and "text_storage_id" in str(e)
                )
            ):
                # Another concurrent process assigned this content - find the existing assignment
                stmt2 = select(EssayStateDB).where(
                    EssayStateDB.batch_id == batch_id,
                    EssayStateDB.text_storage_id == text_storage_id,
                )
                result2 = await session.execute(stmt2)
                existing_essay = result2.scalars().first()

                if existing_essay:
                    logger.info(
                        "Concurrent content assignment detected, returning existing assignment",
                        extra={
                            "batch_id": batch_id,
                            "text_storage_id": text_storage_id,
                            "existing_essay_id": existing_essay.essay_id,
                            "correlation_id": str(correlation_id),
                        },
                    )
                    return False, existing_essay.essay_id

            # Re-raise as processing error for other integrity violations
            raise_processing_error(
                service="essay_lifecycle_service",
                operation="create_essay_state_with_content_idempotency",
                message=f"Database constraint violation: {e.__class__.__name__}",
                correlation_id=correlation_id,
                batch_id=batch_id,
                text_storage_id=text_storage_id,
                error_type=e.__class__.__name__,
                error_details=str(e),
            )

        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_processing_error(
                    service="essay_lifecycle_service",
                    operation="create_essay_state_with_content_idempotency",
                    message=f"Database error during atomic content provisioning: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    text_storage_id=text_storage_id,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )
