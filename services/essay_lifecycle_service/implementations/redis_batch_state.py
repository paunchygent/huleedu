"""
Redis batch state management and lifecycle operations.

Handles batch registration, completion detection, timeout management,
and cleanup operations for distributed batch coordination.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol

    from services.essay_lifecycle_service.implementations.redis_script_manager import (
        RedisScriptManager,
    )

logger = create_service_logger(__name__)


class RedisBatchState:
    """
    Manages batch state, lifecycle, and completion detection in Redis.

    Handles batch registration, completion logic, timeout management,
    and cleanup operations for the distributed batch coordination system.
    """

    def __init__(
        self,
        redis_client: AtomicRedisClientProtocol,
        script_manager: RedisScriptManager,
        default_timeout: int = 86400,  # 24 hours
    ) -> None:
        self._redis = redis_client
        self._script_manager = script_manager
        self._default_timeout = default_timeout
        self._logger = logger

    async def register_batch_slots(
        self,
        batch_id: str,
        essay_ids: list[str],
        metadata: dict[str, Any],
        timeout_seconds: int | None = None,
    ) -> None:
        """
        Initialize available slots for batch with metadata.

        Also processes any pending validation failures that arrived before registration.

        Args:
            batch_id: The batch identifier
            essay_ids: List of essay IDs to use as slots
            metadata: Batch metadata (course_code, user_id, correlation_id, etc.)
            timeout_seconds: Optional timeout override

        Raises:
            HuleEduError: If essay_ids is empty or Redis operation fails
        """
        if not essay_ids:
            correlation_id = metadata.get(
                "correlation_id", UUID("00000000-0000-0000-0000-000000000000")
            )
            error_detail = ErrorDetail(
                error_code=ErrorCode.VALIDATION_ERROR,
                message="Cannot register batch with empty essay_ids",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                service="essay_lifecycle_service",
                operation="register_batch_slots",
                details={"batch_id": batch_id, "metadata": metadata},
            )
            raise HuleEduError(error_detail)

        timeout = timeout_seconds or self._default_timeout
        correlation_id = metadata.get(
            "correlation_id", UUID("00000000-0000-0000-0000-000000000000")
        )

        try:
            # Create transaction pipeline - no watch needed for batch registration
            pipeline = await self._redis.create_transaction_pipeline()
            pipeline.multi()

            # Initialize available slots as a Redis SET
            slots_key = self._script_manager.get_available_slots_key(batch_id)
            pipeline.sadd(slots_key, *essay_ids)

            # Store batch metadata as a Redis HASH
            metadata_key = self._script_manager.get_metadata_key(batch_id)
            # Add expected_count to metadata for completion detection
            metadata_with_count = {**metadata, "expected_count": len(essay_ids)}
            for field, value in metadata_with_count.items():
                # Convert values to strings for Redis storage
                if isinstance(value, dict | list):
                    value_str = json.dumps(value)
                elif isinstance(value, UUID):
                    value_str = str(value)
                elif isinstance(value, datetime):
                    value_str = value.isoformat()
                else:
                    value_str = str(value)
                pipeline.hset(metadata_key, field, value_str)

            # Set TTL for automatic cleanup
            timeout_key = self._script_manager.get_timeout_key(batch_id)
            pipeline.setex(timeout_key, timeout, "timeout_marker")

            # Execute atomic transaction
            results = await pipeline.execute()

            if results is None:
                error_detail = ErrorDetail(
                    error_code=ErrorCode.PROCESSING_ERROR,
                    message=f"Batch registration transaction failed for batch {batch_id}",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    service="essay_lifecycle_service",
                    operation="register_batch_slots",
                    details={"batch_id": batch_id, "essay_count": len(essay_ids)},
                )
                raise HuleEduError(error_detail)

            self._logger.info(
                f"Registered batch {batch_id} with {len(essay_ids)} slots, timeout: {timeout}s"
            )

            # Process any pending validation failures
            await self._process_pending_failures(batch_id, timeout)

        except Exception as e:
            self._logger.error(f"Failed to register batch {batch_id}: {e}", exc_info=True)
            raise

    async def _process_pending_failures(self, batch_id: str, timeout: int) -> None:
        """
        Process pending validation failures that arrived before batch registration.

        Args:
            batch_id: The batch identifier
            timeout: The batch timeout in seconds
        """
        try:
            pending_key = self._script_manager.get_pending_failures_key(batch_id)
            failures_key = self._script_manager.get_validation_failures_key(batch_id)
            slots_key = self._script_manager.get_available_slots_key(batch_id)

            # Get all pending failures
            pending_failures = await self._redis.lrange(pending_key, 0, -1)
            if not pending_failures:
                return

            self._logger.info(
                f"Processing {len(pending_failures)} pending validation failures for batch {batch_id}"
            )

            # Use atomic transaction to move failures and adjust slots
            pipeline = await self._redis.create_transaction_pipeline()
            pipeline.multi()

            # Move failures from pending to actual failures list
            for failure_json in pending_failures:
                pipeline.rpush(failures_key, failure_json)
                # Remove a slot for each failure
                pipeline.spop(slots_key)

            # Delete pending failures key
            pipeline.delete(pending_key)

            # Set TTL on failures key
            pipeline.expire(failures_key, timeout)

            # Execute atomically
            await pipeline.execute()

            self._logger.info(
                f"Processed {len(pending_failures)} pending validation failures for batch {batch_id}"
            )

            # Check if batch is now complete after processing pending failures
            is_complete = await self.check_batch_completion(batch_id)
            if is_complete:
                was_marked = await self.mark_batch_completed_atomically(batch_id)
                if was_marked:
                    self._logger.info(
                        f"Batch {batch_id} marked as completed after processing pending failures"
                    )

        except Exception as e:
            self._logger.error(
                f"Failed to process pending failures for batch {batch_id}: {e}", exc_info=True
            )
            # Don't raise - this is a best-effort operation

    async def check_batch_completion(self, batch_id: str) -> bool:
        """
        Atomically check if batch is complete using comprehensive Redis state.

        A batch is complete when EITHER:
        1. No available slots remaining (all assigned or failed), OR
        2. Total processed (assigned + failed) >= expected count

        AND batch hasn't already been marked completed.

        Args:
            batch_id: The batch identifier

        Returns:
            True if batch is complete, False otherwise

        Raises:
            Exception: If Redis operation fails
        """
        try:
            completion_state = await self._get_completion_state_atomically(batch_id)
            is_complete = self._is_batch_complete(completion_state)

            self._logger.debug(
                f"Batch {batch_id} completion check: "
                f"available={completion_state['available_slots']}, "
                f"assigned={completion_state['assigned_count']}, "
                f"failed={completion_state['failure_count']}, "
                f"expected={completion_state['expected_count']}, "
                f"already_completed={completion_state['already_completed']}, "
                f"complete={is_complete}"
            )
            return is_complete
        except Exception as e:
            self._logger.error(
                f"Failed to check batch completion for {batch_id}: {e}", exc_info=True
            )
            raise

    async def _get_completion_state_atomically(self, batch_id: str) -> dict[str, int]:
        """Get all completion state in single atomic Redis transaction."""
        pipe = await self._redis.create_transaction_pipeline()
        pipe.multi()

        # Get all state atomically
        pipe.scard(self._script_manager.get_available_slots_key(batch_id))  # remaining slots
        pipe.llen(self._script_manager.get_validation_failures_key(batch_id))  # failure count
        pipe.hlen(self._script_manager.get_assignments_key(batch_id))  # assignment count
        pipe.hget(
            self._script_manager.get_metadata_key(batch_id), "expected_count"
        )  # expected count
        pipe.exists(f"batch:{batch_id}:completed")  # completion flag

        results = await pipe.execute()

        return {
            "available_slots": results[0] or 0,
            "failure_count": results[1] or 0,
            "assigned_count": results[2] or 0,
            "expected_count": int(results[3] or 0),
            "already_completed": bool(results[4]),
        }

    def _is_batch_complete(self, state: dict[str, int]) -> bool:
        """
        Single function that determines completion across ALL scenarios.

        Completion criteria:
        1. Either no available slots remaining (all assigned or failed), OR
        2. Total processed (assigned + failed) >= expected count

        Note: The completion flag is used for double-publishing prevention in
        mark_batch_completed_atomically, NOT for completion detection.
        """
        total_processed = state["assigned_count"] + state["failure_count"]
        expected = state["expected_count"]
        no_slots_remaining = state["available_slots"] == 0

        # Batch complete if either all slots consumed OR all files processed
        return no_slots_remaining or (total_processed >= expected)

    async def mark_batch_completed_atomically(self, batch_id: str) -> bool:
        """
        Atomically mark batch as completed to prevent double-completion.

        Args:
            batch_id: The batch identifier

        Returns:
            True if this call marked it completed, False if already completed

        Raises:
            Exception: If Redis operation fails
        """
        # Use SET NX (set if not exists) for atomic completion flag
        result = await self._redis.set_if_not_exists(
            f"batch:{batch_id}:completed",
            "true",
            ttl_seconds=86400,  # 24 hour expiry
        )
        return result  # True if we set it, False if already existed

    async def cleanup_batch(self, batch_id: str) -> None:
        """
        Clean up all Redis keys for a completed batch.

        Args:
            batch_id: The batch identifier

        Raises:
            Exception: If Redis operation fails
        """
        try:
            keys_to_delete = [
                self._script_manager.get_available_slots_key(batch_id),
                self._script_manager.get_assignments_key(batch_id),
                self._script_manager.get_metadata_key(batch_id),
                self._script_manager.get_timeout_key(batch_id),
                self._script_manager.get_content_assignments_key(batch_id),
                self._script_manager.get_validation_failures_key(batch_id),
                self._script_manager.get_pending_failures_key(batch_id),
            ]

            for key in keys_to_delete:
                await self._redis.delete_key(key)

            self._logger.info(f"Cleaned up Redis keys for completed batch {batch_id}")

        except Exception as e:
            self._logger.error(f"Failed to cleanup batch {batch_id}: {e}", exc_info=True)
            raise

    async def handle_batch_timeout(self, batch_id: str) -> dict[str, Any] | None:
        """
        Handle batch timeout by returning current state and cleaning up.

        Args:
            batch_id: The batch identifier

        Returns:
            Final batch status before cleanup, or None if batch not found

        Raises:
            Exception: If Redis operation fails
        """
        try:
            # Import here to avoid circular dependency
            from services.essay_lifecycle_service.implementations.redis_batch_queries import (
                RedisBatchQueries,
            )

            # Create a temporary query service to get final status
            query_service = RedisBatchQueries(self._redis, self._script_manager)
            final_status = await query_service.get_batch_status(batch_id)

            if final_status is None:
                self._logger.warning(f"Batch {batch_id} not found during timeout handling")
                return None

            # Clean up the batch
            await self.cleanup_batch(batch_id)

            self._logger.info(
                f"Handled timeout for batch {batch_id}: "
                f"{final_status['assigned_slots']}/{final_status['total_slots']} slots assigned"
            )

            return final_status

        except Exception as e:
            self._logger.error(f"Failed to handle timeout for batch {batch_id}: {e}", exc_info=True)
            raise
