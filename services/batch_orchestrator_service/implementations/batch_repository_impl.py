"""Batch repository implementation for Batch Orchestrator Service."""

from __future__ import annotations

import asyncio

from common_core.pipeline_models import PhaseName, PipelineExecutionStatus, ProcessingPipelineState
from common_core.status_enums import BatchStatus
from huleedu_service_libs.logging_utils import create_service_logger

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.protocols import BatchRepositoryProtocol


class MockBatchRepositoryImpl(BatchRepositoryProtocol):
    """Mock implementation of BatchRepositoryProtocol for Phase 1.2.

    Simulates production database atomicity behavior to prevent anti-pattern development.
    """

    def __init__(self) -> None:
        """Initialize the mock repository with internal storage."""
        # Storage for batch contexts (course_code, user_id, etc.)
        self.batch_contexts: dict[str, BatchRegistrationRequestV1] = {}
        # Storage for pipeline states (always ProcessingPipelineState objects)
        self.pipeline_states: dict[str, ProcessingPipelineState] = {}
        # Storage for essay data from BatchEssaysReady events
        self.batch_essays: dict[str, list] = {}
        # Simulate database-level locks for atomic operations
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, batch_id: str) -> asyncio.Lock:
        """Get or create a lock for a specific batch (simulates database row-level locking)."""
        if batch_id not in self._locks:
            self._locks[batch_id] = asyncio.Lock()
        return self._locks[batch_id]

    async def get_batch_by_id(self, batch_id: str) -> dict | None:
        """Mock implementation - returns placeholder data."""
        # Note: In production this would return a proper BatchUpload model
        return {"id": batch_id, "status": "pending", "processing_metadata": {}}

    async def create_batch(self, batch_data: dict) -> dict:
        """Mock implementation - returns the batch data with an ID."""
        # Note: In production batch_data would be a BatchUpload model
        return {"id": "mock-batch-id", **batch_data}

    async def update_batch_status(self, batch_id: str, new_status: BatchStatus) -> bool:
        """Mock implementation - always succeeds."""
        return True

    async def save_processing_pipeline_state(self, batch_id: str, pipeline_state: ProcessingPipelineState) -> bool:
        """Mock implementation - stores pipeline state in memory with lock simulation."""
        if not isinstance(pipeline_state, ProcessingPipelineState):
            raise ValueError(f"Expected ProcessingPipelineState, got {type(pipeline_state)}")
        
        async with self._get_lock(batch_id):
            self.pipeline_states[batch_id] = pipeline_state
            return True

    async def get_processing_pipeline_state(self, batch_id: str) -> ProcessingPipelineState | None:
        """Mock implementation - retrieves pipeline state from memory."""
        return self.pipeline_states.get(batch_id)

    async def store_batch_context(
        self,
        batch_id: str,
        registration_data: BatchRegistrationRequestV1,
        correlation_id: str | None = None,
    ) -> bool:
        """Store the full batch context including course info and essay instructions."""
        self.batch_contexts[batch_id] = registration_data
        return True

    async def get_batch_context(self, batch_id: str) -> BatchRegistrationRequestV1 | None:
        """Retrieve the stored batch context for a given batch ID."""
        return self.batch_contexts.get(batch_id)

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

        Simulates production database compare-and-set behavior to prevent race conditions.
        """
        from datetime import datetime, UTC
        
        async with self._get_lock(batch_id):
            current_state = self.pipeline_states.get(batch_id)
            if not current_state:
                # No state exists yet - create a new one
                current_state = ProcessingPipelineState(
                    batch_id=batch_id,
                    requested_pipelines=[]
                )
                self.pipeline_states[batch_id] = current_state

            # Get the pipeline detail for this phase
            pipeline_detail = current_state.get_pipeline(phase_name.value)
            current_status = pipeline_detail.status if pipeline_detail else PipelineExecutionStatus.PENDING_DEPENDENCIES

            # Simulate atomic compare-and-set operation
            if current_status == expected_status:
                # Update status atomically
                if pipeline_detail:
                    pipeline_detail.status = new_status
                    if completion_timestamp:
                        pipeline_detail.completed_at = datetime.fromisoformat(completion_timestamp.replace('Z', '+00:00'))
                else:
                    # Create new pipeline detail if it doesn't exist
                    from common_core.pipeline_models import PipelineStateDetail
                    new_detail = PipelineStateDetail(status=new_status)
                    if completion_timestamp:
                        new_detail.completed_at = datetime.fromisoformat(completion_timestamp.replace('Z', '+00:00'))
                    setattr(current_state, phase_name.value.lower().replace("-", "_"), new_detail)

                current_state.last_updated = datetime.now(UTC)
                return True
            else:
                # Status already changed by another process - operation failed
                return False

    async def store_batch_essays(self, batch_id: str, essays: list) -> bool:
        """Store essay data from BatchEssaysReady event for later pipeline processing."""
        logger = create_service_logger("bos.repository.batch_essays")

        async with self._get_lock(batch_id):
            self.batch_essays[batch_id] = essays
            logger.info(f"Stored {len(essays)} essays for batch {batch_id}")
            logger.debug(f"Essays stored: {[essay.essay_id for essay in essays]}")
            return True

    async def get_batch_essays(self, batch_id: str) -> list | None:
        """Retrieve stored essay data for pipeline processing."""
        logger = create_service_logger("bos.repository.batch_essays")

        essays = self.batch_essays.get(batch_id)
        if essays:
            logger.info(f"Retrieved {len(essays)} essays for batch {batch_id}")
            logger.debug(
                f"Essays retrieved: {[essay.essay_id for essay in essays]}",
            )
        else:
            logger.warning(
                f"No essays found for batch {batch_id}."
                f" Available batches: {list(self.batch_essays.keys())}",
            )
        return essays
