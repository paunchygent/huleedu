"""Basic CRUD operations for Batch Orchestrator Service PostgreSQL implementation."""

from __future__ import annotations

from datetime import UTC, datetime

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select, update

from common_core.status_enums import BatchStatus
from services.batch_orchestrator_service.implementations.batch_database_infrastructure import (
    BatchDatabaseInfrastructure,
)
from services.batch_orchestrator_service.models_db import Batch


class BatchCrudOperations:
    """
    Handles basic CRUD operations for batch records.

    Provides get, create, and update operations for batch entities
    without complex business logic or pipeline state management.
    """

    def __init__(self, db_infrastructure: BatchDatabaseInfrastructure) -> None:
        """Initialize CRUD operations with database infrastructure."""
        self.db = db_infrastructure
        self.logger = create_service_logger("bos.repository.crud")

    async def get_batch_by_id(self, batch_id: str) -> dict | None:
        """Retrieve batch data by ID."""
        async with self.db.session() as session:
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
        async with self.db.session() as session:
            # Extract and validate status
            status_value = batch_data.get("status", BatchStatus.AWAITING_CONTENT_VALIDATION.value)
            if isinstance(status_value, str):
                status = BatchStatus(status_value)
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
        async with self.db.session() as session:
            try:
                # Validate status enum
                status_enum = BatchStatus(new_status)

                stmt = (
                    update(Batch)
                    .where(Batch.id == batch_id)
                    .values(
                        status=status_enum,
                        updated_at=datetime.now(UTC).replace(tzinfo=None),
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
