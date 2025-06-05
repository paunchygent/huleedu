"""Production PostgreSQL repository implementation for Batch Orchestrator Service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from api_models import BatchRegistrationRequestV1
from config import Settings
from enums_db import BatchStatusEnum
from huleedu_service_libs.logging_utils import create_service_logger
from models_db import Base, Batch, ConfigurationSnapshot, PhaseStatusLog
from protocols import BatchRepositoryProtocol
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class PostgreSQLBatchRepositoryImpl(BatchRepositoryProtocol):
    """Production PostgreSQL implementation of BatchRepositoryProtocol."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the PostgreSQL repository with connection settings."""
        self.settings = settings
        self.logger = create_service_logger("bos.repository.postgres")

        # Create async engine with connection pooling
        self.engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_pre_ping=True,  # Validate connections before use
        )

        # Create session maker
        self.async_session_maker = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def initialize_db_schema(self) -> None:
        """Create database tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.logger.info("Database schema initialized")

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

    async def get_batch_by_id(self, batch_id: str) -> dict | None:
        """Retrieve batch data by ID."""
        async with self.session() as session:
            stmt = select(Batch).where(Batch.id == batch_id)
            result = await session.execute(stmt)
            batch = result.scalars().first()

            if batch is None:
                return None

            return {
                "id": batch.id,
                "status": batch.status.value,
                "name": batch.name,
                "description": batch.description,
                "correlation_id": batch.correlation_id,
                "requested_pipelines": batch.requested_pipelines,
                "total_essays": batch.total_essays,
                "processed_essays": batch.processed_essays,
                "version": batch.version,
                "created_at": batch.created_at,
                "updated_at": batch.updated_at,
                "completed_at": batch.completed_at,
                "processing_metadata": batch.processing_metadata,
                "error_details": batch.error_details,
            }

    async def create_batch(self, batch_data: dict) -> dict:
        """Create a new batch record."""
        async with self.session() as session:
            # Extract and validate status
            status_value = batch_data.get(
                "status", BatchStatusEnum.AWAITING_CONTENT_VALIDATION.value
            )
            if isinstance(status_value, str):
                status = BatchStatusEnum(status_value)
            else:
                status = status_value

            batch = Batch(
                id=batch_data["id"],
                correlation_id=batch_data.get("correlation_id"),
                name=batch_data.get("name", f"Batch {batch_data['id'][:8]}"),
                description=batch_data.get("description"),
                status=status,
                requested_pipelines=batch_data.get("requested_pipelines"),
                pipeline_configuration=batch_data.get("pipeline_configuration"),
                total_essays=batch_data.get("total_essays"),
                processed_essays=batch_data.get("processed_essays", 0),
                processing_metadata=batch_data.get("processing_metadata"),
                error_details=batch_data.get("error_details"),
            )

            session.add(batch)
            await session.flush()

            self.logger.info(f"Created batch {batch.id} with status {batch.status.value}")

            return {
                "id": batch.id,
                "status": batch.status.value,
                "name": batch.name,
                "created_at": batch.created_at,
            }

    async def update_batch_status(self, batch_id: str, new_status: str) -> bool:
        """Update the status of an existing batch."""
        async with self.session() as session:
            try:
                # Validate status enum
                status_enum = BatchStatusEnum(new_status)

                stmt = (
                    update(Batch)
                    .where(Batch.id == batch_id)
                    .values(
                        status=status_enum,
                        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    )
                )
                result = await session.execute(stmt)

                if result.rowcount == 0:
                    self.logger.warning(f"Batch {batch_id} not found for status update")
                    return False

                self.logger.info(f"Updated batch {batch_id} status to {new_status}")
                return True

            except ValueError as e:
                self.logger.error(f"Invalid batch status {new_status}: {e}")
                return False
            except Exception as e:
                self.logger.error(f"Failed to update batch {batch_id} status: {e}")
                return False

    async def save_processing_pipeline_state(self, batch_id: str, pipeline_state: dict) -> bool:
        """Save pipeline processing state for a batch."""
        async with self.session() as session:
            try:
                # Check if batch exists
                batch_stmt = select(Batch).where(Batch.id == batch_id)
                batch_result = await session.execute(batch_stmt)
                batch = batch_result.scalars().first()

                if batch is None:
                    self.logger.error(f"Batch {batch_id} not found for pipeline state save")
                    return False

                # Update pipeline configuration and increment version for optimistic locking
                stmt = (
                    update(Batch)
                    .where(Batch.id == batch_id)
                    .values(
                        pipeline_configuration=pipeline_state,
                        version=Batch.version + 1,
                        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    )
                )
                result = await session.execute(stmt)

                if result.rowcount == 0:
                    return False

                self.logger.debug(f"Saved pipeline state for batch {batch_id}")
                return True

            except Exception as e:
                self.logger.error(f"Failed to save pipeline state for batch {batch_id}: {e}")
                return False

    # Start of Selection
    async def get_processing_pipeline_state(self, batch_id: str) -> dict | None:
        """Retrieve pipeline processing state for a batch."""
        async with self.session() as session:
            stmt = select(Batch.pipeline_configuration).where(Batch.id == batch_id)
            result = await session.execute(stmt)
            pipeline_config = result.scalars().first()

            # Ensure we return a dict or None, not Any
            if pipeline_config is None:
                return None
            return dict(pipeline_config) if pipeline_config else None

    async def store_batch_context(
        self, batch_id: str, registration_data: BatchRegistrationRequestV1
    ) -> bool:
        """Store batch context information."""
        async with self.session() as session:
            try:
                # Check if batch exists, if not create it
                batch_stmt = select(Batch).where(Batch.id == batch_id)
                batch_result = await session.execute(batch_stmt)
                batch = batch_result.scalars().first()

                if batch is None:
                    # Create new batch record
                    batch = Batch(
                        id=batch_id,
                        name=(
                            f"{registration_data.course_code} - "
                            f"{registration_data.class_designation}"
                        ),
                        description=registration_data.essay_instructions,
                        status=BatchStatusEnum.AWAITING_CONTENT_VALIDATION,
                        total_essays=registration_data.expected_essay_count,
                        processing_metadata=registration_data.model_dump(),
                    )
                    session.add(batch)
                else:
                    # Update existing batch with context
                    stmt = (
                        update(Batch)
                        .where(Batch.id == batch_id)
                        .values(
                            name=(
                                f"{registration_data.course_code} - "
                                f"{registration_data.class_designation}"
                            ),
                            description=registration_data.essay_instructions,
                            total_essays=registration_data.expected_essay_count,
                            processing_metadata=registration_data.model_dump(),
                            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                        )
                    )
                    await session.execute(stmt)

                self.logger.info(f"Stored batch context for {batch_id}")
                return True

            except Exception as e:
                self.logger.error(f"Failed to store batch context for {batch_id}: {e}")
                return False

    async def get_batch_context(self, batch_id: str) -> BatchRegistrationRequestV1 | None:
        """Retrieve batch context information."""
        async with self.session() as session:
            stmt = select(Batch.processing_metadata).where(Batch.id == batch_id)
            result = await session.execute(stmt)
            metadata = result.scalars().first()

            if metadata is None:
                return None

            try:
                # Convert stored metadata back to BatchRegistrationRequestV1
                return BatchRegistrationRequestV1.model_validate(metadata)
            except Exception as e:
                self.logger.error(f"Failed to deserialize batch context for {batch_id}: {e}")
                return None

    async def update_phase_status_atomically(
        self,
        batch_id: str,
        phase_name: str,
        expected_status: str,
        new_status: str,
        completion_timestamp: str | None = None,
    ) -> bool:
        """
        Atomically update phase status if current status matches expected.

        Uses optimistic locking with version field to prevent race conditions.
        """
        async with self.session() as session:
            try:
                # Get current batch with version for optimistic locking
                batch_stmt = select(Batch).where(Batch.id == batch_id)
                batch_result = await session.execute(batch_stmt)
                batch = batch_result.scalars().first()

                if batch is None:
                    self.logger.error(f"Batch {batch_id} not found for atomic phase update")
                    return False

                # Check current pipeline state
                current_pipeline_state = batch.pipeline_configuration or {}
                current_phase_status = current_pipeline_state.get(f"{phase_name}_status")

                # Atomic compare-and-set operation
                if current_phase_status != expected_status:
                    self.logger.warning(
                        f"Phase {phase_name} status mismatch for batch {batch_id}: "
                        f"expected {expected_status}, got {current_phase_status}"
                    )
                    return False

                # Update pipeline state atomically
                updated_pipeline_state = current_pipeline_state.copy()
                updated_pipeline_state[f"{phase_name}_status"] = new_status

                if completion_timestamp:
                    updated_pipeline_state[f"{phase_name}_completed_at"] = completion_timestamp

                # Use optimistic locking with version field
                stmt = (
                    update(Batch)
                    .where(Batch.id == batch_id, Batch.version == batch.version)
                    .values(
                        pipeline_configuration=updated_pipeline_state,
                        version=Batch.version + 1,
                        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    )
                )
                result = await session.execute(stmt)

                if result.rowcount == 0:
                    self.logger.warning(
                        f"Optimistic lock failed for batch {batch_id} phase {phase_name} update"
                    )
                    return False

                # Log the phase status change
                phase_log = PhaseStatusLog(
                    batch_id=batch_id,
                    phase=phase_name,
                    status=new_status,
                    phase_completed_at=datetime.fromisoformat(completion_timestamp).replace(tzinfo=None)
                    if completion_timestamp
                    else None,
                    processing_metadata={"previous_status": expected_status},
                )
                session.add(phase_log)

                self.logger.info(
                    f"Atomically updated batch {batch_id} phase {phase_name}: "
                    f"{expected_status} -> {new_status}"
                )
                return True

            except Exception as e:
                self.logger.error(
                    f"Failed atomic phase update for batch {batch_id} phase {phase_name}: {e}"
                )
                return False

    async def create_configuration_snapshot(
        self,
        batch_id: str,
        snapshot_name: str,
        pipeline_definition: dict,
        configuration_version: str,
        description: str | None = None,
    ) -> bool:
        """Create a configuration snapshot for a batch."""
        async with self.session() as session:
            try:
                snapshot = ConfigurationSnapshot(
                    batch_id=batch_id,
                    snapshot_name=snapshot_name,
                    description=description,
                    pipeline_definition=pipeline_definition,
                    configuration_version=configuration_version,
                    validation_status="valid",
                )

                session.add(snapshot)
                self.logger.info(
                    f"Created configuration snapshot {snapshot_name} for batch {batch_id}"
                )
                return True

            except IntegrityError as e:
                self.logger.error(f"Configuration snapshot creation failed (integrity): {e}")
                return False
            except Exception as e:
                self.logger.error(f"Failed to create configuration snapshot: {e}")
                return False

    async def get_phase_status_history(self, batch_id: str) -> list[dict[str, Any]]:
        """Get phase status history for a batch."""
        async with self.session() as session:
            stmt = (
                select(PhaseStatusLog)
                .where(PhaseStatusLog.batch_id == batch_id)
                .order_by(PhaseStatusLog.created_at)
            )
            result = await session.execute(stmt)
            logs = result.scalars().all()

            return [
                {
                    "id": log.id,
                    "phase": log.phase.value,
                    "status": log.status.value,
                    "phase_started_at": log.phase_started_at,
                    "phase_completed_at": log.phase_completed_at,
                    "essays_processed": log.essays_processed,
                    "essays_failed": log.essays_failed,
                    "error_message": log.error_message,
                    "correlation_id": log.correlation_id,
                    "created_at": log.created_at,
                    "processing_metadata": log.processing_metadata,
                }
                for log in logs
            ]
