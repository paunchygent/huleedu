"""Batch repository implementation for Batch Orchestrator Service."""

from __future__ import annotations

import asyncio
from typing import Dict

from api_models import BatchRegistrationRequestV1
from huleedu_service_libs.logging_utils import create_service_logger
from protocols import BatchRepositoryProtocol


class MockBatchRepositoryImpl(BatchRepositoryProtocol):
    """Mock implementation of BatchRepositoryProtocol for Phase 1.2.

    Simulates production database atomicity behavior to prevent anti-pattern development.
    """

    def __init__(self) -> None:
        """Initialize the mock repository with internal storage."""
        # Storage for batch contexts (course_code, class_designation, etc.)
        self.batch_contexts: dict[str, BatchRegistrationRequestV1] = {}
        # Storage for pipeline states
        self.pipeline_states: dict[str, dict] = {}
        # Storage for essay data from BatchEssaysReady events
        self.batch_essays: dict[str, list] = {}
        # Simulate database-level locks for atomic operations
        self._locks: Dict[str, asyncio.Lock] = {}

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

    async def update_batch_status(self, batch_id: str, new_status: str) -> bool:
        """Mock implementation - always succeeds."""
        return True

    async def save_processing_pipeline_state(self, batch_id: str, pipeline_state: dict) -> bool:
        """Mock implementation - stores pipeline state in memory with lock simulation."""
        async with self._get_lock(batch_id):
            self.pipeline_states[batch_id] = pipeline_state
            return True

    async def get_processing_pipeline_state(self, batch_id: str) -> dict | None:
        """Mock implementation - retrieves pipeline state from memory."""
        return self.pipeline_states.get(batch_id)

    async def store_batch_context(
        self, batch_id: str, registration_data: BatchRegistrationRequestV1
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
        phase_name: str,
        expected_status: str,
        new_status: str,
        completion_timestamp: str | None = None,
    ) -> bool:
        """
        Atomically update phase status if current status matches expected.

        Simulates production database compare-and-set behavior to prevent race conditions.
        """
        async with self._get_lock(batch_id):
            current_state = self.pipeline_states.get(batch_id, {})
            current_status = current_state.get(f"{phase_name}_status")

            # Simulate atomic compare-and-set operation
            if current_status == expected_status:
                # Update status atomically
                updated_state = current_state.copy()
                updated_state[f"{phase_name}_status"] = new_status
                if completion_timestamp:
                    updated_state[f"{phase_name}_completed_at"] = completion_timestamp

                self.pipeline_states[batch_id] = updated_state
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
            logger.debug(f"Essays stored: {[essay.get('essay_id', 'unknown') for essay in essays]}")
            return True

    async def get_batch_essays(self, batch_id: str) -> list | None:
        """Retrieve stored essay data for pipeline processing."""
        logger = create_service_logger("bos.repository.batch_essays")

        essays = self.batch_essays.get(batch_id)
        if essays:
            logger.info(f"Retrieved {len(essays)} essays for batch {batch_id}")
            logger.debug(f"Essays retrieved: {[essay.get('essay_id', 'unknown') for essay in essays]}")
        else:
            logger.warning(f"No essays found for batch {batch_id}. Available batches: {list(self.batch_essays.keys())}")
        return essays
