"""Batch context operations for Batch Orchestrator Service PostgreSQL implementation."""

from __future__ import annotations

from datetime import UTC, datetime

from api_models import BatchRegistrationRequestV1
from huleedu_service_libs.logging_utils import create_service_logger
from implementations.batch_database_infrastructure import BatchDatabaseInfrastructure
from models_db import Batch
from sqlalchemy import select, update

from common_core.enums import BatchStatus


class BatchContextOperations:
    """
    Handles batch context storage and retrieval operations.

    Provides operations for storing and retrieving batch registration
    context information including course data and processing metadata.
    """

    def __init__(self, db_infrastructure: BatchDatabaseInfrastructure) -> None:
        """Initialize context operations with database infrastructure."""
        self.db = db_infrastructure
        self.logger = create_service_logger("bos.repository.context")

    async def store_batch_context(
        self,
        batch_id: str,
        registration_data: BatchRegistrationRequestV1,
    ) -> bool:
        """Store batch context information."""
        async with self.db.session() as session:
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
                        status=BatchStatus.AWAITING_CONTENT_VALIDATION,
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
                            updated_at=datetime.now(UTC).replace(tzinfo=None),
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
        async with self.db.session() as session:
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
