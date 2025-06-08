"""Pipeline state management for Batch Orchestrator Service PostgreSQL implementation."""

from __future__ import annotations

from datetime import datetime, timezone

from huleedu_service_libs.logging_utils import create_service_logger
from implementations.batch_database_infrastructure import BatchDatabaseInfrastructure
from models_db import Batch, PhaseStatusLog
from sqlalchemy import select, update


class BatchPipelineStateManager:
    """
    Handles pipeline state management and atomic operations.

    Provides pipeline configuration storage, retrieval, and atomic
    phase status updates with optimistic locking for race condition prevention.
    """

    def __init__(self, db_infrastructure: BatchDatabaseInfrastructure) -> None:
        """Initialize pipeline state manager with database infrastructure."""
        self.db = db_infrastructure
        self.logger = create_service_logger("bos.repository.pipeline")

    async def save_processing_pipeline_state(self, batch_id: str, pipeline_state: dict) -> bool:
        """Save pipeline processing state for a batch."""
        async with self.db.session() as session:
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

                return True

            except Exception as e:
                self.logger.error(f"Failed to save pipeline state for batch {batch_id}: {e}")
                return False

    async def get_processing_pipeline_state(self, batch_id: str) -> dict | None:
        """Retrieve pipeline processing state for a batch."""
        async with self.db.session() as session:
            stmt = select(Batch.pipeline_configuration).where(Batch.id == batch_id)
            result = await session.execute(stmt)
            pipeline_config = result.scalars().first()

            # Ensure we return a dict or None, not Any
            if pipeline_config is None:
                return None
            return dict(pipeline_config) if pipeline_config else None

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
        async with self.db.session() as session:
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
                    phase_completed_at=datetime.fromisoformat(completion_timestamp).replace(
                        tzinfo=None
                    )
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
