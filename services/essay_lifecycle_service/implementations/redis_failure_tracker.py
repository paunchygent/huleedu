"""
Redis validation failure tracking for batch coordination.

Handles validation failure storage, retrieval, and coordination with
batch registration for race condition handling.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol

    from services.essay_lifecycle_service.implementations.redis_script_manager import (
        RedisScriptManager,
    )

logger = create_service_logger(__name__)


class RedisFailureTracker:
    """
    Tracks validation failures and manages pending failures in Redis.

    Handles race conditions where validation failures arrive before
    batch registration and ensures atomic failure tracking operations.
    """

    def __init__(
        self, redis_client: AtomicRedisClientProtocol, script_manager: RedisScriptManager
    ) -> None:
        self._redis = redis_client
        self._script_manager = script_manager
        self._logger = logger

    async def track_validation_failure(self, batch_id: str, failure: dict[str, Any]) -> None:
        """
        Track a validation failure for a batch atomically.

        If batch doesn't exist yet, stores the failure as pending to be processed
        when the batch is registered. This handles race conditions where validation
        failures arrive before batch registration.

        Args:
            batch_id: The batch identifier
            failure: Validation failure data (will be JSON-encoded)

        Raises:
            Exception: If Redis operation fails
        """
        try:
            # Check if batch exists by looking for metadata
            metadata_key = self._script_manager.get_metadata_key(batch_id)
            batch_exists = await self._redis.exists(metadata_key)
            failure_json = json.dumps(failure)

            if not batch_exists:
                # Batch not registered yet - store as pending failure
                pending_key = self._script_manager.get_pending_failures_key(batch_id)
                await self._redis.rpush(pending_key, failure_json)
                # Set TTL on pending failures to prevent memory leak
                await self._redis.expire(pending_key, 86400)  # 24 hours

                self._logger.info(
                    f"Stored pending validation failure for unregistered batch {batch_id}: "
                    f"{failure.get('original_file_name', 'unknown')}"
                )
                return

            # Batch exists - process normally
            failures_key = self._script_manager.get_validation_failures_key(batch_id)
            slots_key = self._script_manager.get_available_slots_key(batch_id)

            # Use atomic transaction to ensure both operations succeed or fail together
            pipeline = await self._redis.create_transaction_pipeline()
            pipeline.multi()

            # Add to list of failures
            pipeline.rpush(failures_key, failure_json)

            # Remove a slot from available slots to account for the validation failure
            # Note: We use SPOP (not SREM) because validation failures occur BEFORE
            # slot assignment, so there's no specific essay_id to remove. We just need
            # to reduce the available slot count by one.
            pipeline.spop(slots_key)

            # Execute atomically
            results = await pipeline.execute()
            removed_slot = results[1] if len(results) > 1 else None

            if removed_slot:
                # Decode bytes to string for logging
                slot_str = (
                    removed_slot.decode("utf-8")
                    if isinstance(removed_slot, bytes)
                    else removed_slot
                )
                self._logger.debug(
                    f"Removed slot {slot_str} from available slots for batch {batch_id} "
                    f"due to validation failure"
                )

            # Set TTL to match batch timeout
            timeout_key = self._script_manager.get_timeout_key(batch_id)
            timeout_exists = await self._redis.get(timeout_key) is not None
            if timeout_exists:
                # Match TTL to batch timeout
                ttl = await self._redis.ttl(timeout_key)
                if ttl > 0:
                    await self._redis.expire(failures_key, ttl)

            self._logger.info(
                f"Tracked validation failure for batch {batch_id}: "
                f"{failure.get('original_file_name', 'unknown')}"
            )

            # Check if batch is now complete after tracking failure
            # Import here to avoid circular dependency
            from services.essay_lifecycle_service.implementations.redis_batch_state import (
                RedisBatchState,
            )

            batch_state = RedisBatchState(self._redis, self._script_manager)
            is_complete = await batch_state.check_batch_completion(batch_id)
            if is_complete:
                was_marked = await batch_state.mark_batch_completed_atomically(batch_id)
                if was_marked:
                    self._logger.info(
                        f"Batch {batch_id} marked as completed after validation failure"
                    )

        except Exception as e:
            self._logger.error(
                f"Failed to track validation failure for batch {batch_id}: {e}", exc_info=True
            )
            raise

    async def get_validation_failures(self, batch_id: str) -> list[dict[str, Any]]:
        """
        Get all validation failures for a batch.

        Args:
            batch_id: The batch identifier

        Returns:
            List of validation failure dictionaries

        Raises:
            Exception: If Redis operation fails
        """
        try:
            failures_key = self._script_manager.get_validation_failures_key(batch_id)
            failure_jsons = await self._redis.lrange(failures_key, 0, -1)

            if not failure_jsons:
                return []

            # Parse JSON failures
            failures = []
            for failure_json in failure_jsons:
                try:
                    failures.append(json.loads(failure_json))
                except json.JSONDecodeError as e:
                    self._logger.warning(
                        f"Failed to parse validation failure for batch {batch_id}: {e}"
                    )
                    # Skip corrupted entries
                    continue

            return failures

        except Exception as e:
            self._logger.error(
                f"Failed to get validation failures for batch {batch_id}: {e}", exc_info=True
            )
            raise

    async def get_validation_failure_count(self, batch_id: str) -> int:
        """
        Get count of validation failures for a batch.

        Args:
            batch_id: The batch identifier

        Returns:
            Number of validation failures

        Raises:
            Exception: If Redis operation fails
        """
        try:
            failures_key = self._script_manager.get_validation_failures_key(batch_id)
            count = await self._redis.llen(failures_key)
            return count or 0

        except Exception as e:
            self._logger.error(
                f"Failed to get validation failure count for batch {batch_id}: {e}", exc_info=True
            )
            raise
