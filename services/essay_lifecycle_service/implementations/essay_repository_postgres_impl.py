"""
Production PostgreSQL repository implementation for Essay Lifecycle Service.

Following the pattern established by BOS PostgreSQL implementation with
proper connection pooling, transaction management, and enum handling.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.domain_enums import ContentType

# EntityReference removed - using primitive parameters
from common_core.status_enums import EssayStatus
from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring
from huleedu_service_libs.error_handling import (
    raise_connection_error,
    raise_processing_error,
    raise_resource_not_found,
)
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select, update
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.constants import get_els_phase_statuses
from services.essay_lifecycle_service.domain_models import EssayState as ConcreteEssayState
from services.essay_lifecycle_service.models_db import Base, EssayStateDB
from services.essay_lifecycle_service.protocols import EssayRepositoryProtocol

if TYPE_CHECKING:
    from services.essay_lifecycle_service.protocols import EssayState


class PostgreSQLEssayRepository(EssayRepositoryProtocol):
    """Production PostgreSQL implementation of EssayRepositoryProtocol."""

    def __init__(self, settings: Settings, database_metrics: DatabaseMetrics | None = None) -> None:
        """Initialize the PostgreSQL repository with connection settings and optional database metrics."""
        self.settings = settings
        self.logger = create_service_logger("els.repository.postgres")
        self.database_metrics = database_metrics

        # Create async engine with connection pooling
        self.engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            future=True,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
            pool_recycle=settings.DATABASE_POOL_RECYCLE,
        )

        # Setup database monitoring if metrics are provided
        if self.database_metrics:
            setup_database_monitoring(self.engine, "els", self.database_metrics.get_metrics())
            self.logger.info("Database monitoring enabled for ELS")

        # Create session maker
        self.async_session_maker = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def initialize_db_schema(self, correlation_id: UUID | None = None) -> None:
        """Create database tables if they don't exist."""
        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            from uuid import uuid4

            correlation_id = uuid4()
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            self.logger.info("Essay Lifecycle Service database schema initialized")
        except Exception as e:
            raise_connection_error(
                service="essay_lifecycle_service",
                operation="initialize_db_schema",
                target="database",
                message=f"Failed to initialize database schema: {e.__class__.__name__}",
                correlation_id=correlation_id,
                error_type=e.__class__.__name__,
                error_details=str(e),
                database_url=str(self.settings.DATABASE_URL),
            )

    async def run_migrations(self, correlation_id: UUID | None = None) -> None:
        """Run Alembic migrations to apply all constraints and indexes."""
        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            from uuid import uuid4

            correlation_id = uuid4()
        try:
            # For tests, we'll manually apply the constraints instead of using Alembic
            # This avoids the async event loop conflict
            async with self.engine.begin() as conn:
                # Execute each migration step separately (asyncpg requirement)

                # Add text_storage_id column if it doesn't exist
                await conn.execute(
                    sa_text("""
                    ALTER TABLE essay_states
                    ADD COLUMN IF NOT EXISTS text_storage_id VARCHAR(255)
                """)
                )

                # Create index if it doesn't exist
                await conn.execute(
                    sa_text("""
                    CREATE INDEX IF NOT EXISTS ix_essay_states_text_storage_id
                    ON essay_states(text_storage_id)
                """)
                )

                # Create partial unique index (replacing the old constraint)
                # This allows multiple NULL text_storage_id values in the same batch
                await conn.execute(
                    sa_text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_essay_content_idempotency_partial
                    ON essay_states (batch_id, text_storage_id)
                    WHERE text_storage_id IS NOT NULL
                """)
                )

                # Add foreign key constraint if it doesn't exist
                await conn.execute(
                    sa_text("""
                    DO $$ BEGIN
                        ALTER TABLE essay_states
                        ADD CONSTRAINT fk_essay_states_batch_id
                        FOREIGN KEY (batch_id) REFERENCES batch_essay_trackers(batch_id)
                        ON DELETE SET NULL;
                    EXCEPTION
                        WHEN duplicate_object THEN NULL;
                    END $$
                """)
                )

            self.logger.info("Essay Lifecycle Service migrations applied successfully")
        except Exception as e:
            raise_connection_error(
                service="essay_lifecycle_service",
                operation="run_migrations",
                target="database",
                message=f"Failed to run migrations: {e.__class__.__name__}",
                correlation_id=correlation_id,
                error_type=e.__class__.__name__,
                error_details=str(e),
                database_url=str(self.settings.DATABASE_URL),
            )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for database sessions with proper transaction handling."""
        session = self.async_session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    def get_session_factory(self) -> async_sessionmaker:
        """Get the session factory for transaction management."""
        return self.async_session_maker

    def _db_to_essay_state(self, db_essay: EssayStateDB) -> ConcreteEssayState:
        """Convert database model to EssayState."""
        # Convert timeline from string to datetime
        timeline_converted = {k: datetime.fromisoformat(v) for k, v in db_essay.timeline.items()}

        return ConcreteEssayState(
            essay_id=db_essay.essay_id,
            batch_id=db_essay.batch_id,
            current_status=db_essay.current_status,
            processing_metadata=db_essay.processing_metadata,
            timeline=timeline_converted,
            storage_references={ContentType(k): v for k, v in db_essay.storage_references.items()},
            created_at=db_essay.created_at,
            updated_at=db_essay.updated_at,
        )

    def _essay_state_to_db_dict(self, essay_state: EssayState) -> dict[str, Any]:
        """Convert EssayState to database dictionary."""
        return {
            "essay_id": essay_state.essay_id,
            "batch_id": essay_state.batch_id,
            "current_status": essay_state.current_status,
            "processing_metadata": essay_state.processing_metadata,
            "timeline": {k: v.isoformat() for k, v in essay_state.timeline.items()},
            "storage_references": {k.value: v for k, v in essay_state.storage_references.items()},
            "created_at": essay_state.created_at.replace(tzinfo=None),
            "updated_at": essay_state.updated_at.replace(tzinfo=None),
        }

    async def get_essay_state(self, essay_id: str, session: AsyncSession | None = None) -> ConcreteEssayState | None:
        """Retrieve essay state by ID."""
        if session is None:
            async with self.session() as session:
                return await self.get_essay_state(essay_id, session)
        
        stmt = select(EssayStateDB).where(EssayStateDB.essay_id == essay_id)
        result = await session.execute(stmt)
        db_essay = result.scalars().first()

        if db_essay is None:
            return None

        return self._db_to_essay_state(db_essay)

    async def update_essay_state(
        self,
        essay_id: str,
        new_status: EssayStatus,
        metadata: dict[str, Any],
        session: AsyncSession | None = None,
        storage_reference: tuple[ContentType, str] | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        """Update essay state with new status, metadata, and optional storage reference."""
        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            from uuid import uuid4

            correlation_id = uuid4()

        if session is None:
            async with self.session() as session:
                return await self.update_essay_state(
                    essay_id, new_status, metadata, session, storage_reference, correlation_id
                )

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
            current_state = self._db_to_essay_state(db_essay)

            # Log the transition for debugging
            self.logger.debug(
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

            self.logger.debug(f"Updated essay {essay_id} status to {new_status.value}")

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

    async def update_essay_status_via_machine(
        self,
        essay_id: str,
        new_status: EssayStatus,
        metadata: dict[str, Any],
        session: AsyncSession | None = None,
        storage_reference: tuple[ContentType, str] | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        """Update essay state using status from state machine."""
        await self.update_essay_state(
            essay_id,
            new_status,
            metadata,
            session,
            storage_reference=storage_reference,
            correlation_id=correlation_id,
        )

    async def create_essay_record(
        self,
        essay_id: str,
        batch_id: str | None = None,
        entity_type: str = "essay",
        session: AsyncSession | None = None,
        correlation_id: UUID | None = None,
    ) -> ConcreteEssayState:
        """Create new essay record from primitive parameters."""
        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            from uuid import uuid4

            correlation_id = uuid4()

        if session is None:
            async with self.session() as session:
                return await self.create_essay_record(
                    essay_id, batch_id, entity_type, session, correlation_id
                )

        try:
            # Debug logging to trace batch_id issue
            self.logger.info(f"Creating essay {essay_id} with batch_id: {batch_id}")

            essay_state = ConcreteEssayState(
                essay_id=essay_id,
                batch_id=batch_id,
                current_status=EssayStatus.UPLOADED,
                timeline={EssayStatus.UPLOADED.value: datetime.now(UTC)},
            )

            db_data = self._essay_state_to_db_dict(essay_state)
            db_essay = EssayStateDB(**db_data)
            session.add(db_essay)

            self.logger.info(f"Created essay record {essay_id}")
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
        essay_data: list[dict[str, str | None]],
        session: AsyncSession | None = None,
        correlation_id: UUID | None = None,
    ) -> list[EssayState]:
        """Create multiple essay records in single atomic transaction.

        Args:
            essay_data: List of dicts with keys: essay_id, batch_id, entity_type
        """
        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            from uuid import uuid4

            correlation_id = uuid4()

        if session is None:
            async with self.session() as session:
                return await self.create_essay_records_batch(essay_data, session, correlation_id)

        if not essay_data:
            return []

        try:
            # Log batch creation start
            batch_id = essay_data[0].get("parent_id", "unknown") if essay_data else "unknown"
            essay_ids = [data.get("entity_id", "unknown") for data in essay_data]
            self.logger.info(
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
                db_data = self._essay_state_to_db_dict(essay_state)
                db_essay = EssayStateDB(**db_data)
                session.add(db_essay)

            # All essays are committed together in a single transaction
            self.logger.info(
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
        essay_id: str,
        metadata_updates: dict[str, Any],
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Update essay processing metadata fields."""
        if session is None:
            async with self.session() as session:
                return await self.update_essay_processing_metadata(
                    essay_id, metadata_updates, correlation_id, session
                )

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

            self.logger.debug(f"Updated processing metadata for essay {essay_id}")

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
        essay_id: str,
        student_id: str | None,
        association_confirmed_at: Any,  # datetime
        association_method: str,
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Update essay with student association from Phase 1 matching."""
        if session is None:
            async with self.session() as session:
                return await self.update_student_association(
                    essay_id,
                    student_id,
                    association_confirmed_at,
                    association_method,
                    correlation_id,
                    session,
                )

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

            self.logger.debug(
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

    async def list_essays_by_batch(self, batch_id: str) -> list[EssayState]:
        """List all essays in a batch."""
        async with self.session() as session:
            stmt = select(EssayStateDB).where(EssayStateDB.batch_id == batch_id)
            result = await session.execute(stmt)
            db_essays = result.scalars().all()

            essays: list[EssayState] = []
            for db_essay in db_essays:
                essay_state = self._db_to_essay_state(db_essay)
                essays.append(essay_state)  # type: ignore[arg-type]

            return essays

    async def get_batch_status_summary(self, batch_id: str) -> dict[EssayStatus, int]:
        """Get status count breakdown for a batch using efficient SQL aggregation."""
        from sqlalchemy import func

        async with self.session() as session:
            # Use SQL GROUP BY aggregation for optimal performance
            stmt = (
                select(EssayStateDB.current_status, func.count().label("count"))
                .where(EssayStateDB.batch_id == batch_id)
                .group_by(EssayStateDB.current_status)
            )
            result = await session.execute(stmt)
            rows = result.all()

            # Convert to dictionary with EssayStatus enum keys
            summary: dict[EssayStatus, int] = {}
            for status_value, count in rows:
                summary[status_value] = count

            return summary

    async def get_batch_summary_with_essays(
        self, batch_id: str
    ) -> tuple[list[EssayState], dict[EssayStatus, int]]:
        """Get both essays and status summary for a batch in single operation (prevents N+1 queries)."""
        # Fetch essays once
        essays = await self.list_essays_by_batch(batch_id)

        # Compute status summary from already-fetched essays
        summary: dict[EssayStatus, int] = {}
        for essay in essays:
            status = essay.current_status
            summary[status] = summary.get(status, 0) + 1

        return essays, summary

    async def get_essay_by_text_storage_id_and_batch_id(
        self, batch_id: str, text_storage_id: str
    ) -> ConcreteEssayState | None:
        """Retrieve essay state by text_storage_id and batch_id for idempotency checking."""
        async with self.session() as session:
            # Query essays with matching storage reference and batch
            stmt = select(EssayStateDB).where(EssayStateDB.batch_id == batch_id)
            result = await session.execute(stmt)
            db_essays = result.scalars().all()

            # Check storage references for matching text_storage_id
            for db_essay in db_essays:
                storage_refs = db_essay.storage_references
                if storage_refs.get(ContentType.ORIGINAL_ESSAY.value) == text_storage_id:
                    return self._db_to_essay_state(db_essay)

            return None

    async def create_or_update_essay_state_for_slot_assignment(
        self,
        internal_essay_id: str,
        batch_id: str,
        text_storage_id: str,
        original_file_name: str,
        file_size: int,
        content_hash: str | None,
        initial_status: EssayStatus,
        session: AsyncSession | None = None,
        correlation_id: UUID | None = None,
    ) -> ConcreteEssayState:
        """Create or update essay state for slot assignment with content metadata."""
        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            from uuid import uuid4

            correlation_id = uuid4()

        if session is None:
            async with self.session() as session:
                return await self.create_or_update_essay_state_for_slot_assignment(
                    internal_essay_id,
                    batch_id,
                    text_storage_id,
                    original_file_name,
                    file_size,
                    content_hash,
                    initial_status,
                    session,
                    correlation_id,
                )

        try:
            # Check if essay already exists
            existing_essay = await self.get_essay_state(internal_essay_id)

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

                await self.update_essay_state(
                    internal_essay_id,
                    initial_status,
                    metadata,
                    session,
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

                db_data = self._essay_state_to_db_dict(essay_state)
                db_essay = EssayStateDB(**db_data)
                session.add(db_essay)

                self.logger.info(f"Created essay {internal_essay_id} for slot assignment")
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

    async def list_essays_by_batch_and_phase(
        self, batch_id: str, phase_name: str, session: AsyncSession | None = None
    ) -> list[EssayState]:
        """List all essays in a batch that are part of a specific processing phase."""
        try:
            phase_statuses = get_els_phase_statuses(phase_name)
        except ValueError as e:
            self.logger.warning(f"Unknown phase: {phase_name} - {e}")
            return []

        # Declare essays list once
        essays: list[EssayState] = []

        # Use provided session or create new one
        if session is not None:
            stmt = select(EssayStateDB).where(
                EssayStateDB.batch_id == batch_id,
                EssayStateDB.current_status.in_(phase_statuses),
            )
            result = await session.execute(stmt)
            db_essays = result.scalars().all()

            for db_essay in db_essays:
                essay_state = self._db_to_essay_state(db_essay)
                essays.append(essay_state)  # type: ignore[arg-type]

            return essays
        else:
            async with self.session() as session:
                stmt = select(EssayStateDB).where(
                    EssayStateDB.batch_id == batch_id,
                    EssayStateDB.current_status.in_(phase_statuses),
                )
                result = await session.execute(stmt)
                db_essays = result.scalars().all()

                for db_essay in db_essays:
                    essay_state = self._db_to_essay_state(db_essay)
                    essays.append(essay_state)  # type: ignore[arg-type]

                return essays

    async def create_essay_state_with_content_idempotency(
        self,
        batch_id: str,
        text_storage_id: str,
        essay_data: dict[str, Any],
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> tuple[bool, str | None]:
        """
        Create essay state with atomic idempotency check for content provisioning.

        This method addresses ELS-002 Phase 1 requirements by providing database-level
        atomicity for content provisioning to prevent race conditions.

        Args:
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
        if session is None:
            async with self.session() as session:
                return await self.create_essay_state_with_content_idempotency(
                    batch_id, text_storage_id, essay_data, correlation_id, session
                )

        try:
            # Use SELECT FOR UPDATE for row-level locking to prevent concurrent assignments
            # First check if this content is already assigned to any essay in this batch
            stmt = (
                select(EssayStateDB)
                .where(
                    EssayStateDB.batch_id == batch_id,
                    EssayStateDB.text_storage_id == text_storage_id,
                )
                .with_for_update()
            )
            result = await session.execute(stmt)
            existing_essay = result.scalars().first()

            if existing_essay is not None:
                # Content already assigned - idempotent success case
                self.logger.info(
                    "Content already assigned to essay, returning existing assignment",
                    extra={
                        "batch_id": batch_id,
                        "text_storage_id": text_storage_id,
                        "existing_essay_id": existing_essay.essay_id,
                        "correlation_id": str(correlation_id),
                    },
                )
                return False, existing_essay.essay_id

            # Get internal essay ID
            internal_essay_id = essay_data["internal_essay_id"]
            initial_status = essay_data.get("initial_status", EssayStatus.READY_FOR_PROCESSING)

            # Check if essay already exists (created during batch registration)
            existing_stmt = select(EssayStateDB).where(EssayStateDB.essay_id == internal_essay_id)
            existing_result = await session.execute(existing_stmt)
            existing_essay_db = existing_result.scalars().first()

            if existing_essay_db:
                # Update existing essay with content information
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
                db_data = self._essay_state_to_db_dict(essay_state)
                # Explicitly set text_storage_id for the constraint
                db_data["text_storage_id"] = text_storage_id

                db_essay = EssayStateDB(**db_data)
                session.add(db_essay)

            # No commit here - let the handler manage the transaction

            self.logger.info(
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
                stmt = select(EssayStateDB).where(
                    EssayStateDB.batch_id == batch_id,
                    EssayStateDB.text_storage_id == text_storage_id,
                )
                result = await session.execute(stmt)
                existing_essay = result.scalars().first()

                if existing_essay:
                    self.logger.info(
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
