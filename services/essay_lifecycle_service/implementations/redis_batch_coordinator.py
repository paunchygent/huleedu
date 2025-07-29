"""
Redis-based batch coordinator using composition of domain-focused classes.

Provides the same interface as the original RedisBatchCoordinator but
with internal composition of specialized domain classes for better
separation of concerns and maintainability.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol

    from services.essay_lifecycle_service.config import Settings

from services.essay_lifecycle_service.implementations.redis_batch_queries import RedisBatchQueries
from services.essay_lifecycle_service.implementations.redis_batch_state import RedisBatchState
from services.essay_lifecycle_service.implementations.redis_failure_tracker import (
    RedisFailureTracker,
)
from services.essay_lifecycle_service.implementations.redis_script_manager import RedisScriptManager
from services.essay_lifecycle_service.implementations.redis_slot_operations import (
    RedisSlotOperations,
)

logger = create_service_logger(__name__)


class RedisBatchCoordinator:
    """
    Redis-based distributed batch coordinator using composition of domain classes.

    Implements distributed slot assignment using Redis operations through
    specialized domain classes for better separation of concerns:
    - RedisScriptManager: Handles Lua scripts and key generation
    - RedisSlotOperations: Manages slot assignment/return operations
    - RedisBatchState: Handles batch lifecycle and completion logic
    - RedisBatchQueries: Provides read-only operations
    - RedisFailureTracker: Manages validation failure tracking

    This maintains the same interface as the original RedisBatchCoordinator
    while providing better internal organization and maintainability.
    """

    def __init__(self, redis_client: AtomicRedisClientProtocol, settings: Settings) -> None:
        self._redis = redis_client
        self._settings = settings
        self._logger = logger

        # Initialize domain-focused components
        self._script_manager = RedisScriptManager(redis_client)
        self._slot_operations = RedisSlotOperations(redis_client, self._script_manager)
        self._batch_state = RedisBatchState(
            redis_client,
            self._script_manager,
            default_timeout=86400,  # 24 hours
        )
        self._batch_queries = RedisBatchQueries(redis_client, self._script_manager)
        self._failure_tracker = RedisFailureTracker(redis_client, self._script_manager)

    # Slot Assignment Operations (delegate to RedisSlotOperations)
    async def assign_slot_atomic(
        self, batch_id: str, content_metadata: dict[str, Any], correlation_id: UUID | None = None
    ) -> str | None:
        """Atomically assign an available slot to content using a Lua script."""
        return await self._slot_operations.assign_slot_atomic(
            batch_id, content_metadata, correlation_id
        )

    async def return_slot(
        self, batch_id: str, text_storage_id: str, correlation_id: UUID | None = None
    ) -> bool:
        """Atomically return a previously assigned slot to the available pool."""
        return await self._slot_operations.return_slot(batch_id, text_storage_id, correlation_id)

    async def get_available_slot_count(self, batch_id: str) -> int:
        """Get the number of available slots remaining for a batch."""
        return await self._slot_operations.get_available_slot_count(batch_id)

    async def get_assigned_count(self, batch_id: str) -> int:
        """Get count of assigned slots for a batch."""
        return await self._slot_operations.get_assigned_count(batch_id)

    async def get_essay_id_for_content(self, batch_id: str, text_storage_id: str) -> str | None:
        """Get the essay ID assigned to a specific text_storage_id."""
        return await self._slot_operations.get_essay_id_for_content(batch_id, text_storage_id)

    # Batch State Management (delegate to RedisBatchState)
    async def register_batch_slots(
        self,
        batch_id: str,
        essay_ids: list[str],
        metadata: dict[str, Any],
        timeout_seconds: int | None = None,
    ) -> None:
        """Initialize available slots for batch with metadata."""
        return await self._batch_state.register_batch_slots(
            batch_id, essay_ids, metadata, timeout_seconds
        )

    async def check_batch_completion(self, batch_id: str) -> bool:
        """Atomically check if batch is complete using comprehensive Redis state."""
        return await self._batch_state.check_batch_completion(batch_id)

    async def mark_batch_completed_atomically(self, batch_id: str) -> bool:
        """Atomically mark batch as completed to prevent double-completion."""
        return await self._batch_state.mark_batch_completed_atomically(batch_id)

    async def cleanup_batch(self, batch_id: str) -> None:
        """Clean up all Redis keys for a completed batch."""
        return await self._batch_state.cleanup_batch(batch_id)

    async def handle_batch_timeout(self, batch_id: str) -> dict[str, Any] | None:
        """Handle batch timeout by returning current state and cleaning up."""
        return await self._batch_state.handle_batch_timeout(batch_id)

    # Batch Query Operations (delegate to RedisBatchQueries)
    async def get_batch_assignments(self, batch_id: str) -> dict[str, dict[str, Any]]:
        """Get all current slot assignments for a batch."""
        return await self._batch_queries.get_batch_assignments(batch_id)

    async def get_batch_metadata(self, batch_id: str) -> dict[str, Any] | None:
        """Get batch metadata from Redis."""
        return await self._batch_queries.get_batch_metadata(batch_id)

    async def get_batch_status(self, batch_id: str) -> dict[str, Any] | None:
        """Get comprehensive batch status from Redis."""
        return await self._batch_queries.get_batch_status(batch_id)

    async def get_assigned_essays(self, batch_id: str) -> list[dict[str, Any]]:
        """Get all assigned essay metadata for a batch."""
        return await self._batch_queries.get_assigned_essays(batch_id)

    async def get_missing_slots(self, batch_id: str) -> list[str]:
        """Get list of unassigned slot IDs for a batch."""
        return await self._batch_queries.get_missing_slots(batch_id)

    async def list_active_batch_ids(self) -> list[str]:
        """List all active batch IDs by scanning Redis metadata keys."""
        return await self._batch_queries.list_active_batch_ids()

    async def find_batch_for_essay(self, essay_id: str) -> tuple[str, str] | None:
        """Find the batch and user_id for a given essay by scanning batch assignments."""
        return await self._batch_queries.find_batch_for_essay(essay_id)

    # Validation Failure Tracking (delegate to RedisFailureTracker)
    async def track_validation_failure(self, batch_id: str, failure: dict[str, Any]) -> None:
        """Track a validation failure for a batch atomically."""
        return await self._failure_tracker.track_validation_failure(batch_id, failure)

    async def get_validation_failures(self, batch_id: str) -> list[dict[str, Any]]:
        """Get all validation failures for a batch."""
        return await self._failure_tracker.get_validation_failures(batch_id)

    async def get_validation_failure_count(self, batch_id: str) -> int:
        """Get count of validation failures for a batch."""
        return await self._failure_tracker.get_validation_failure_count(batch_id)
