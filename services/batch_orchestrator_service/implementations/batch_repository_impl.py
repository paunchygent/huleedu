"""Batch repository implementation for Batch Orchestrator Service."""

from __future__ import annotations

from api_models import BatchRegistrationRequestV1
from protocols import BatchRepositoryProtocol


class MockBatchRepositoryImpl(BatchRepositoryProtocol):
    """Mock implementation of BatchRepositoryProtocol for Phase 1.2."""

    def __init__(self) -> None:
        """Initialize the mock repository with internal storage."""
        # Storage for batch contexts (course_code, class_designation, etc.)
        self.batch_contexts: dict[str, BatchRegistrationRequestV1] = {}
        # Storage for pipeline states
        self.pipeline_states: dict[str, dict] = {}

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
        """Mock implementation - stores pipeline state in memory."""
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
