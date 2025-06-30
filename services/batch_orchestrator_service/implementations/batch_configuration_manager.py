"""Configuration management for Batch Orchestrator Service PostgreSQL implementation."""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from services.batch_orchestrator_service.implementations.batch_database_infrastructure import BatchDatabaseInfrastructure
from services.batch_orchestrator_service.models_db import ConfigurationSnapshot, PhaseStatusLog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


class BatchConfigurationManager:
    """
    Handles configuration snapshots and phase status history.

    Provides operations for creating configuration snapshots and retrieving
    phase status history for audit trails and debugging purposes.
    """

    def __init__(self, db_infrastructure: BatchDatabaseInfrastructure) -> None:
        """Initialize configuration manager with database infrastructure."""
        self.db = db_infrastructure
        self.logger = create_service_logger("bos.repository.configuration")

    async def create_configuration_snapshot(
        self,
        batch_id: str,
        snapshot_name: str,
        pipeline_definition: dict,
        configuration_version: str,
        description: str | None = None,
    ) -> bool:
        """Create a configuration snapshot for a batch."""
        async with self.db.session() as session:
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
                    f"Created configuration snapshot {snapshot_name} for batch {batch_id}",
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
        async with self.db.session() as session:
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
