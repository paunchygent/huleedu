"""
Database query operations for Essay Lifecycle Service.

Contains all read and write operations that interact with the database,
following SRP and DDD principles.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus
from huleedu_service_libs.error_handling import (
    raise_processing_error,
    raise_resource_not_found,
)
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.essay_lifecycle_service.constants import get_els_phase_statuses
from services.essay_lifecycle_service.domain_models import EssayState as ConcreteEssayState
from services.essay_lifecycle_service.implementations.essay_repository_mappers import (
    EssayRepositoryMappers,
)
from services.essay_lifecycle_service.models_db import EssayStateDB

if TYPE_CHECKING:
    from services.essay_lifecycle_service.protocols import EssayState

logger = create_service_logger("els.repository.queries")


class EssayRepositoryQueries:
    """Database query operations for essay states."""

    def __init__(self) -> None:
        """Initialize queries class."""
        self.mappers = EssayRepositoryMappers()

    async def get_essay_state(
        self, session: AsyncSession, essay_id: str
    ) -> ConcreteEssayState | None:
        """Retrieve essay state by ID."""
        stmt = select(EssayStateDB).where(EssayStateDB.essay_id == essay_id)
        result = await session.execute(stmt)
        db_essay = result.scalars().first()

        if db_essay is None:
            return None

        return self.mappers.db_to_essay_state(db_essay)

    async def list_essays_by_batch(self, session: AsyncSession, batch_id: str) -> list[EssayState]:
        """List all essays in a batch."""
        stmt = select(EssayStateDB).where(EssayStateDB.batch_id == batch_id)
        result = await session.execute(stmt)
        db_essays = result.scalars().all()

        essays: list[EssayState] = []
        for db_essay in db_essays:
            essay_state = self.mappers.db_to_essay_state(db_essay)
            essays.append(essay_state)  # type: ignore[arg-type]

        return essays

    async def get_batch_status_summary(
        self, session: AsyncSession, batch_id: str
    ) -> dict[EssayStatus, int]:
        """Get status count breakdown for a batch using efficient SQL aggregation."""
        # Use SQL GROUP BY aggregation for optimal performance
        stmt = (
            select(EssayStateDB.current_status, func.count().label("count"))
            .where(EssayStateDB.batch_id == batch_id)
            .group_by(EssayStateDB.current_status)
        )
        result = await session.execute(stmt)
        rows = result.all()

        # Convert to dictionary with EssayStatus enum keys
        status_summary: dict[EssayStatus, int] = {}
        for status_value, count in rows:
            status_summary[status_value] = count

        return status_summary

    async def get_batch_summary_with_essays(
        self, session: AsyncSession, batch_id: str
    ) -> tuple[list[EssayState], dict[EssayStatus, int]]:
        """Get both essays and status summary for a batch in single operation (prevents N+1 queries)."""
        # Fetch essays once
        essays = await self.list_essays_by_batch(session, batch_id)

        # Compute status summary from already-fetched essays
        summary: dict[EssayStatus, int] = {}
        for essay in essays:
            status = essay.current_status
            summary[status] = summary.get(status, 0) + 1

        return essays, summary

    async def get_essay_by_text_storage_id_and_batch_id(
        self, session: AsyncSession, batch_id: str, text_storage_id: str
    ) -> ConcreteEssayState | None:
        """Retrieve essay state by text_storage_id and batch_id for idempotency checking."""
        # Query essays with matching storage reference and batch
        stmt = select(EssayStateDB).where(EssayStateDB.batch_id == batch_id)
        result = await session.execute(stmt)
        db_essays = result.scalars().all()

        # Check storage references for matching text_storage_id
        for db_essay in db_essays:
            storage_refs = db_essay.storage_references
            if storage_refs.get(ContentType.ORIGINAL_ESSAY.value) == text_storage_id:
                return self.mappers.db_to_essay_state(db_essay)

        return None

    async def list_essays_by_batch_and_phase(
        self, session: AsyncSession, batch_id: str, phase_name: str
    ) -> list[EssayState]:
        """List all essays in a batch that are part of a specific processing phase."""
        try:
            phase_statuses = get_els_phase_statuses(phase_name)
        except ValueError as e:
            logger.warning(f"Unknown phase: {phase_name} - {e}")
            return []

        stmt = select(EssayStateDB).where(
            EssayStateDB.batch_id == batch_id,
            EssayStateDB.current_status.in_(phase_statuses),
        )
        result = await session.execute(stmt)
        db_essays = result.scalars().all()

        essays: list[EssayState] = []
        for db_essay in db_essays:
            essay_state = self.mappers.db_to_essay_state(db_essay)
            essays.append(essay_state)  # type: ignore[arg-type]

        return essays

    async def update_essay_state(
        self,
        session: AsyncSession,
        essay_id: str,
        new_status: EssayStatus,
        metadata: dict[str, Any],
        storage_reference: tuple[ContentType, str] | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        """Update essay state with new status, metadata, and optional storage reference."""
        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            from uuid import uuid4

            correlation_id = uuid4()

        try:
            # Use SELECT FOR UPDATE to prevent race conditions
            stmt = select(EssayStateDB).where(EssayStateDB.essay_id == essay_id).with_for_update()
            result = await session.execute(stmt)
            db_essay = result.scalars().first()

            if db_essay is None:
                raise_resource_not_found(
                    service="essay_lifecycle_service",
                    operation="update_essay_state",
                    resource_type="Essay",
                    resource_id=essay_id,
                    correlation_id=correlation_id,
                )

            # Convert to ConcreteEssayState
            current_state = self.mappers.db_to_essay_state(db_essay)

            # Log the transition for debugging
            logger.debug(
                f"Updating essay {essay_id} from {current_state.current_status.value} to {new_status.value}"
            )

            # Update the state object
            current_state.update_status(new_status, metadata)
            if storage_reference:
                content_type, storage_id = storage_reference
                current_state.storage_references[content_type] = storage_id

            # Convert timeline to proper format for JSON storage
            timeline_for_db = {k: v.isoformat() for k, v in current_state.timeline.items()}

            # Convert storage_references keys (ContentType enum) to strings for JSONB
            storage_references_for_db = {
                k.value: v for k, v in current_state.storage_references.items()
            }

            update_stmt = (
                update(EssayStateDB)
                .where(EssayStateDB.essay_id == essay_id)
                .values(
                    current_status=current_state.current_status,
                    processing_metadata=current_state.processing_metadata,
                    storage_references=storage_references_for_db,
                    timeline=timeline_for_db,
                    batch_id=current_state.batch_id,
                    updated_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            update_result = await session.execute(update_stmt)

            if update_result.rowcount == 0:
                raise_resource_not_found(
                    service="essay_lifecycle_service",
                    operation="update_essay_state",
                    resource_type="Essay",
                    resource_id=essay_id,
                    correlation_id=correlation_id,
                    operation_details="Essay update failed after successful selection",
                )

            logger.debug(f"Updated essay {essay_id} status to {new_status.value}")

        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_processing_error(
                    service="essay_lifecycle_service",
                    operation="update_essay_state",
                    message=f"Database error during essay state update: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    essay_id=essay_id,
                    new_status=new_status.value,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def create_essay_record(
        self,
        session: AsyncSession,
        essay_id: str,
        batch_id: str | None = None,
        entity_type: str = "essay",
        correlation_id: UUID | None = None,
    ) -> ConcreteEssayState:
        """Create new essay record from primitive parameters."""
        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            from uuid import uuid4

            correlation_id = uuid4()

        try:
            # Debug logging to trace batch_id issue
            logger.info(f"Creating essay {essay_id} with batch_id: {batch_id}")

            essay_state = ConcreteEssayState(
                essay_id=essay_id,
                batch_id=batch_id,
                current_status=EssayStatus.UPLOADED,
                timeline={EssayStatus.UPLOADED.value: datetime.now(UTC)},
            )

            db_data = self.mappers.essay_state_to_db_dict(essay_state)
            db_essay = EssayStateDB(**db_data)
            session.add(db_essay)

            logger.info(f"Created essay record {essay_id}")
            return essay_state

        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_processing_error(
                    service="essay_lifecycle_service",
                    operation="create_essay_record",
                    message=f"Database error during essay creation: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    essay_id=essay_id,
                    batch_id=batch_id,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def create_essay_records_batch(
        self,
        session: AsyncSession,
        essay_data: list[dict[str, str | None]],
        correlation_id: UUID | None = None,
    ) -> list[EssayState]:
        """Create multiple essay records in single atomic transaction."""
        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            from uuid import uuid4

            correlation_id = uuid4()

        if not essay_data:
            return []

        try:
            # Log batch creation start
            batch_id = essay_data[0].get("parent_id", "unknown") if essay_data else "unknown"
            essay_ids = [data.get("entity_id", "unknown") for data in essay_data]
            logger.info(
                f"Creating batch of {len(essay_data)} essay records for batch {batch_id}: {essay_ids}"
            )

            # Create essay states for all references
            essay_states: list[EssayState] = []
            for data in essay_data:
                essay_state: EssayState = ConcreteEssayState(
                    essay_id=data["entity_id"],
                    batch_id=data.get("parent_id"),
                    current_status=EssayStatus.UPLOADED,
                    timeline={EssayStatus.UPLOADED.value: datetime.now(UTC)},
                )
                essay_states.append(essay_state)

            # Single atomic transaction for all essay records
            for essay_state in essay_states:
                db_data = self.mappers.essay_state_to_db_dict(essay_state)
                db_essay = EssayStateDB(**db_data)
                session.add(db_essay)

            # Flush to make essays visible to subsequent queries in the same transaction
            # This is critical for content provisioning to find the essays
            await session.flush()

            # All essays are committed together in a single transaction
            logger.info(
                f"Successfully created batch of {len(essay_states)} essay records for batch {batch_id}"
            )
            return essay_states

        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                batch_id = essay_data[0].get("parent_id", "unknown") if essay_data else "unknown"
                raise_processing_error(
                    service="essay_lifecycle_service",
                    operation="create_essay_records_batch",
                    message=f"Database error during batch essay creation: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    essay_count=len(essay_data),
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def update_essay_processing_metadata(
        self,
        session: AsyncSession,
        essay_id: str,
        metadata_updates: dict[str, Any],
        correlation_id: UUID,
    ) -> None:
        """Update essay processing metadata fields."""
        try:
            # Use SELECT FOR UPDATE to prevent race conditions
            stmt = select(EssayStateDB).where(EssayStateDB.essay_id == essay_id).with_for_update()
            result = await session.execute(stmt)
            db_essay = result.scalars().first()

            if db_essay is None:
                raise_resource_not_found(
                    service="essay_lifecycle_service",
                    operation="update_essay_processing_metadata",
                    resource_type="Essay",
                    resource_id=essay_id,
                    correlation_id=correlation_id,
                )

            # Merge updates into existing processing metadata
            updated_metadata = {**db_essay.processing_metadata, **metadata_updates}

            # Update the database record
            update_stmt = (
                update(EssayStateDB)
                .where(EssayStateDB.essay_id == essay_id)
                .values(
                    processing_metadata=updated_metadata,
                    updated_at=datetime.now(UTC).replace(tzinfo=None),
                    version=db_essay.version + 1,
                )
            )
            update_result = await session.execute(update_stmt)

            if update_result.rowcount == 0:
                raise_resource_not_found(
                    service="essay_lifecycle_service",
                    operation="update_essay_processing_metadata",
                    resource_type="Essay",
                    resource_id=essay_id,
                    correlation_id=correlation_id,
                    operation_details="Essay metadata update failed after successful selection",
                )

            logger.debug(f"Updated processing metadata for essay {essay_id}")

        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_processing_error(
                    service="essay_lifecycle_service",
                    operation="update_essay_processing_metadata",
                    message=f"Database error during metadata update: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    essay_id=essay_id,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def update_student_association(
        self,
        session: AsyncSession,
        essay_id: str,
        student_id: str | None,
        association_confirmed_at: Any,  # datetime
        association_method: str,
        correlation_id: UUID,
    ) -> None:
        """Update essay with student association from Phase 1 matching."""
        try:
            # Use SELECT FOR UPDATE to prevent race conditions
            stmt = select(EssayStateDB).where(EssayStateDB.essay_id == essay_id).with_for_update()
            result = await session.execute(stmt)
            db_essay = result.scalars().first()

            if db_essay is None:
                raise_resource_not_found(
                    service="essay_lifecycle_service",
                    operation="update_student_association",
                    resource_type="Essay",
                    resource_id=essay_id,
                    correlation_id=correlation_id,
                )

            # Convert association_confirmed_at to datetime if needed
            confirmed_at_datetime = association_confirmed_at
            if isinstance(association_confirmed_at, str):
                confirmed_at_datetime = datetime.fromisoformat(
                    association_confirmed_at.replace("Z", "+00:00")
                )
            elif association_confirmed_at is not None and hasattr(
                association_confirmed_at, "replace"
            ):
                # Handle timezone-aware datetime by converting to naive UTC
                confirmed_at_datetime = association_confirmed_at.replace(tzinfo=None)

            # Update the database record
            update_stmt = (
                update(EssayStateDB)
                .where(EssayStateDB.essay_id == essay_id)
                .values(
                    student_id=student_id,
                    association_confirmed_at=confirmed_at_datetime,
                    association_method=association_method,
                    updated_at=datetime.now(UTC).replace(tzinfo=None),
                    version=db_essay.version + 1,
                )
            )
            update_result = await session.execute(update_stmt)

            if update_result.rowcount == 0:
                raise_resource_not_found(
                    service="essay_lifecycle_service",
                    operation="update_student_association",
                    resource_type="Essay",
                    resource_id=essay_id,
                    correlation_id=correlation_id,
                    operation_details="Essay student association update failed after successful selection",
                )

            logger.debug(
                f"Updated student association for essay {essay_id} with student {student_id}"
            )

        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_processing_error(
                    service="essay_lifecycle_service",
                    operation="update_student_association",
                    message=f"Database error during student association update: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    essay_id=essay_id,
                    student_id=student_id,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )
