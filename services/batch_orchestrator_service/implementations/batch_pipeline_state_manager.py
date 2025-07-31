"""Pipeline state management for Batch Orchestrator Service PostgreSQL implementation."""

from __future__ import annotations

from datetime import UTC, datetime

from common_core.pipeline_models import PhaseName, PipelineExecutionStatus, ProcessingPipelineState
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select, update

from services.batch_orchestrator_service.enums_db import PhaseStatusEnum
from services.batch_orchestrator_service.implementations.batch_database_infrastructure import (
    BatchDatabaseInfrastructure,
)
from services.batch_orchestrator_service.models_db import Batch, PhaseStatusLog


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

    def _map_pipeline_status_to_phase_status(
        self, status: PipelineExecutionStatus
    ) -> PhaseStatusEnum:
        """Map PipelineExecutionStatus to PhaseStatusEnum for database storage."""
        mapping = {
            PipelineExecutionStatus.PENDING_DEPENDENCIES: PhaseStatusEnum.PENDING,
            PipelineExecutionStatus.DISPATCH_INITIATED: PhaseStatusEnum.INITIATED,
            PipelineExecutionStatus.IN_PROGRESS: PhaseStatusEnum.IN_PROGRESS,
            PipelineExecutionStatus.COMPLETED_SUCCESSFULLY: PhaseStatusEnum.COMPLETED,
            PipelineExecutionStatus.COMPLETED_WITH_PARTIAL_SUCCESS: PhaseStatusEnum.COMPLETED,
            PipelineExecutionStatus.FAILED: PhaseStatusEnum.FAILED,
            PipelineExecutionStatus.CANCELLED: PhaseStatusEnum.CANCELLED,
            PipelineExecutionStatus.SKIPPED_DUE_TO_DEPENDENCY_FAILURE: PhaseStatusEnum.FAILED,
            PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG: PhaseStatusEnum.CANCELLED,
            PipelineExecutionStatus.REQUESTED_BY_USER: PhaseStatusEnum.PENDING,
        }
        return mapping.get(status, PhaseStatusEnum.FAILED)

    async def save_processing_pipeline_state(
        self, batch_id: str, pipeline_state: ProcessingPipelineState
    ) -> bool:
        """Save pipeline processing state for a batch."""
        if not isinstance(pipeline_state, ProcessingPipelineState):
            raise ValueError(f"Expected ProcessingPipelineState, got {type(pipeline_state)}")

        async with self.db.session() as session:
            try:
                # Check if batch exists
                batch_stmt = select(Batch).where(Batch.id == batch_id)
                batch_result = await session.execute(batch_stmt)
                batch = batch_result.scalars().first()

                if batch is None:
                    self.logger.error(f"Batch {batch_id} not found for pipeline state save")
                    return False

                # Convert ProcessingPipelineState to dict for JSON storage
                # Use mode="json" to properly serialize datetime fields to ISO strings
                pipeline_state_dict = pipeline_state.model_dump(mode="json")

                # Update pipeline configuration and increment version for optimistic locking
                stmt = (
                    update(Batch)
                    .where(Batch.id == batch_id)
                    .values(
                        pipeline_configuration=pipeline_state_dict,
                        version=Batch.version + 1,
                        updated_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                )
                result = await session.execute(stmt)

                if result.rowcount == 0:
                    return False

                return True

            except Exception as e:
                self.logger.error(f"Failed to save pipeline state for batch {batch_id}: {e}")
                return False

    async def get_processing_pipeline_state(self, batch_id: str) -> ProcessingPipelineState | None:
        """Retrieve pipeline processing state for a batch."""
        async with self.db.session() as session:
            stmt = select(Batch.pipeline_configuration).where(Batch.id == batch_id)
            result = await session.execute(stmt)
            pipeline_config = result.scalars().first()

            if pipeline_config is None:
                return None

            # Convert dict from database back to ProcessingPipelineState
            try:
                if isinstance(pipeline_config, dict):
                    return ProcessingPipelineState.model_validate(pipeline_config)
                else:
                    self.logger.warning(
                        f"Invalid pipeline configuration type for batch {batch_id}: "
                        f"{type(pipeline_config)}"
                    )
                    return None
            except Exception as e:
                self.logger.error(f"Failed to deserialize pipeline state for batch {batch_id}: {e}")
                return None

    async def update_phase_status_atomically(
        self,
        batch_id: str,
        phase_name: PhaseName,
        expected_status: PipelineExecutionStatus,
        new_status: PipelineExecutionStatus,
        completion_timestamp: str | None = None,
        correlation_id: str | None = None,
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

                # Check current pipeline state - convert from dict to
                # ProcessingPipelineState if needed
                current_pipeline_dict = batch.pipeline_configuration or {}
                if current_pipeline_dict:
                    try:
                        current_pipeline_state = ProcessingPipelineState.model_validate(
                            current_pipeline_dict
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Failed to deserialize pipeline state for batch {batch_id}: {e}"
                        )
                        return False
                else:
                    # Create new pipeline state if none exists
                    current_pipeline_state = ProcessingPipelineState(
                        batch_id=batch_id, requested_pipelines=[]
                    )

                # Get current phase status
                pipeline_detail = current_pipeline_state.get_pipeline(phase_name.value)
                current_phase_status = (
                    pipeline_detail.status
                    if pipeline_detail
                    else PipelineExecutionStatus.PENDING_DEPENDENCIES
                )

                # Atomic compare-and-set operation
                if current_phase_status != expected_status:
                    self.logger.warning(
                        f"Phase {phase_name} status mismatch for batch {batch_id}: "
                        f"expected {expected_status.value}, got {current_phase_status.value}",
                    )
                    return False

                # Update pipeline state atomically
                if pipeline_detail:
                    pipeline_detail.status = new_status
                    if completion_timestamp:
                        pipeline_detail.completed_at = datetime.fromisoformat(
                            completion_timestamp.replace("Z", "+00:00")
                        )
                else:
                    # Create new pipeline detail if it doesn't exist
                    from common_core.pipeline_models import PipelineStateDetail

                    new_detail = PipelineStateDetail(status=new_status)
                    if completion_timestamp:
                        new_detail.completed_at = datetime.fromisoformat(
                            completion_timestamp.replace("Z", "+00:00")
                        )
                    setattr(
                        current_pipeline_state,
                        phase_name.value.lower().replace("-", "_"),
                        new_detail,
                    )

                current_pipeline_state.last_updated = datetime.now(UTC)
                # Use mode="json" to properly serialize datetime fields to ISO strings
                updated_pipeline_dict = current_pipeline_state.model_dump(mode="json")

                # Use optimistic locking with version field
                stmt = (
                    update(Batch)
                    .where(Batch.id == batch_id, Batch.version == batch.version)
                    .values(
                        pipeline_configuration=updated_pipeline_dict,
                        version=Batch.version + 1,
                        updated_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                )
                result = await session.execute(stmt)

                if result.rowcount == 0:
                    self.logger.warning(
                        f"Optimistic lock failed for batch {batch_id} phase {phase_name} update",
                    )
                    return False

                # Log the phase status change
                phase_log = PhaseStatusLog(
                    batch_id=batch_id,
                    phase=phase_name,
                    status=self._map_pipeline_status_to_phase_status(new_status),
                    correlation_id=correlation_id
                    or batch_id,  # Use correlation_id or fall back to batch_id
                    phase_completed_at=datetime.fromisoformat(completion_timestamp).replace(
                        tzinfo=None,
                    )
                    if completion_timestamp
                    else None,
                    processing_metadata={"previous_status": expected_status.value},
                )
                session.add(phase_log)

                self.logger.info(
                    f"Atomically updated batch {batch_id} phase {phase_name}: "
                    f"{expected_status} -> {new_status}",
                )
                return True

            except Exception as e:
                self.logger.error(
                    f"Failed atomic phase update for batch {batch_id} phase {phase_name}: {e}",
                )
                return False

    async def record_phase_failure(
        self,
        batch_id: str,
        phase_name: PhaseName,
        error: HuleEduError,
        correlation_id: str,
    ) -> bool:
        """
        Record a phase failure with structured error details.

        This method creates a PhaseStatusLog entry with proper error_details
        populated from the HuleEduError instance.
        """
        from huleedu_service_libs.error_handling import HuleEduError

        async with self.db.session() as session:
            try:
                # Create phase status log with error details
                phase_log = PhaseStatusLog(
                    batch_id=batch_id,
                    phase=phase_name,
                    status=PhaseStatusEnum.FAILED,
                    correlation_id=correlation_id,
                    phase_started_at=datetime.now(UTC).replace(tzinfo=None),
                    error_details=error.error_detail.model_dump()
                    if isinstance(error, HuleEduError)
                    else {
                        "error_code": "PROCESSING_ERROR",
                        "message": str(error),
                        "service": "batch_orchestrator_service",
                        "operation": f"phase_{phase_name.value}_execution",
                        "correlation_id": correlation_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    processing_metadata={
                        "failure_recorded_at": datetime.now(UTC).isoformat(),
                    },
                )
                session.add(phase_log)

                # Also update the batch's error_details
                stmt = (
                    update(Batch)
                    .where(Batch.id == batch_id)
                    .values(
                        error_details=phase_log.error_details,
                        updated_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                )
                await session.execute(stmt)

                await session.commit()

                self.logger.info(
                    f"Recorded phase failure for batch {batch_id} phase {phase_name}",
                    extra={"correlation_id": correlation_id},
                )
                return True

            except Exception as e:
                self.logger.error(
                    f"Failed to record phase failure for batch {batch_id}: {e}",
                    exc_info=True,
                )
                return False
