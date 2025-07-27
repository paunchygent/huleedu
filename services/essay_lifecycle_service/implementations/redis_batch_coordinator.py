"""
Redis-based batch coordinator for distributed slot assignment.

Replaces in-memory batch state management with atomic Redis operations
to enable horizontal scaling and eliminate race conditions in slot assignment.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from redis.exceptions import WatchError

if TYPE_CHECKING:
    from services.essay_lifecycle_service.config import Settings


logger = create_service_logger(__name__)


class RedisBatchCoordinator:
    """
    Redis-based distributed batch coordinator using atomic operations.

    Implements distributed slot assignment using Redis SET operations to eliminate
    race conditions present in the in-memory implementation.

    Redis Key Structure:
    - batch:{batch_id}:available_slots -> SET of essay_ids available for assignment
    - batch:{batch_id}:assignments -> HASH of essay_id -> content_metadata JSON
    - batch:{batch_id}:metadata -> HASH of batch metadata (course_code, user_id, etc.)
    - batch:{batch_id}:timeout -> Key with TTL for batch timeout management
    """

    def __init__(self, redis_client: AtomicRedisClientProtocol, settings: Settings) -> None:
        self._redis = redis_client
        self._settings = settings
        self._logger = logger
        self._default_timeout = (
            86400  # 24 hours for complex processing including overnight LLM batches
        )

    def _get_available_slots_key(self, batch_id: str) -> str:
        """Get Redis key for available slots set."""
        return f"batch:{batch_id}:available_slots"

    def _get_assignments_key(self, batch_id: str) -> str:
        """Get Redis key for assignments hash."""
        return f"batch:{batch_id}:assignments"

    def _get_metadata_key(self, batch_id: str) -> str:
        """Get Redis key for batch metadata hash."""
        return f"batch:{batch_id}:metadata"

    def _get_timeout_key(self, batch_id: str) -> str:
        """Get Redis key for batch timeout tracking."""
        return f"batch:{batch_id}:timeout"

    def _get_content_assignments_key(self, batch_id: str) -> str:
        """Get Redis key for content assignments hash (text_storage_id -> essay_id mapping)."""
        return f"batch:{batch_id}:content_assignments"

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
        """
        if not essay_ids:
            raise ValueError("Cannot register batch with empty essay_ids")

        timeout = timeout_seconds or self._default_timeout

        try:
            # Create transaction pipeline - no watch needed for batch registration
            pipeline = await self._redis.create_transaction_pipeline()
            pipeline.multi()

            # Initialize available slots as a Redis SET
            slots_key = self._get_available_slots_key(batch_id)
            pipeline.sadd(slots_key, *essay_ids)

            # Store batch metadata as a Redis HASH
            metadata_key = self._get_metadata_key(batch_id)
            for field, value in metadata.items():
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
            timeout_key = self._get_timeout_key(batch_id)
            pipeline.setex(timeout_key, timeout, "timeout_marker")

            # Execute atomic transaction
            results = await pipeline.execute()

            if results is None:
                raise RuntimeError(f"Batch registration transaction failed for batch {batch_id}")

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
            pending_key = self._get_pending_failures_key(batch_id)
            failures_key = self._get_validation_failures_key(batch_id)
            slots_key = self._get_available_slots_key(batch_id)

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
            results = await pipeline.execute()

            self._logger.info(
                f"Processed {len(pending_failures)} pending validation failures for batch {batch_id}"
            )

        except Exception as e:
            self._logger.error(
                f"Failed to process pending failures for batch {batch_id}: {e}", exc_info=True
            )
            # Don't raise - this is a best-effort operation

    async def assign_slot_atomic(
        self, batch_id: str, content_metadata: dict[str, Any]
    ) -> str | None:
        """
        Atomically assign an available slot to content using a full Redis transaction
        with retries on WatchError.

        Args:
            batch_id: The batch identifier
            content_metadata: Content metadata including text_storage_id

        Returns:
            The assigned internal essay ID if successful, None if no slots are available
            or if a race condition caused the transaction to fail after retries.
        """
        text_storage_id = content_metadata.get("text_storage_id")
        if not text_storage_id:
            raise ValueError("content_metadata must include text_storage_id")

        for attempt in range(self._settings.redis_transaction_retries):
            try:
                return await self._attempt_slot_assignment(
                    batch_id, text_storage_id, content_metadata
                )
            except WatchError:
                if attempt < self._settings.redis_transaction_retries - 1:
                    delay = (2**attempt) * 0.01 + random.uniform(0, 0.01)
                    self._logger.warning(
                        f"WatchError on attempt {attempt + 1} for {text_storage_id}, retrying in {delay:.3f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    self._logger.error(
                        f"Final attempt failed for {text_storage_id} due to WatchError."
                    )
                    return None

        return None  # Should not be reached, but for safety

    async def _attempt_slot_assignment(
        self, batch_id: str, text_storage_id: str, content_metadata: dict[str, Any]
    ) -> str | None:
        slots_key = self._get_available_slots_key(batch_id)
        content_assignments_key = self._get_content_assignments_key(batch_id)
        assignments_key = self._get_assignments_key(batch_id)

        # Check for duplicate content BEFORE starting transaction
        existing_assignment = await self._redis.hget(content_assignments_key, text_storage_id)
        if existing_assignment:
            assignment_str = (
                existing_assignment.decode("utf-8")
                if isinstance(existing_assignment, bytes)
                else existing_assignment
            )
            self._logger.info(
                f"Content {text_storage_id} already assigned to essay {assignment_str} "
                f"in batch {batch_id} (idempotent operation)"
            )
            return assignment_str

        # Check for available slots BEFORE starting transaction
        available_slots = await self._redis.smembers(slots_key)
        if not available_slots:
            self._logger.warning(f"No available slots in batch {batch_id}.")
            return None

        async with await self._redis.create_transaction_pipeline(
            slots_key, content_assignments_key
        ) as pipe:

            # Start the transaction
            pipe.multi()

            # Pop a slot and perform assignments
            assigned_essay_id = available_slots.pop()
            pipe.srem(slots_key, assigned_essay_id)
            pipe.hset(content_assignments_key, text_storage_id, assigned_essay_id)
            pipe.hset(assignments_key, assigned_essay_id, json.dumps(content_metadata))

            # Execute the transaction. Throws WatchError if optimistic lock fails.
            await pipe.execute()

            # Decode bytes to string for return
            essay_id_str = (
                assigned_essay_id.decode("utf-8")
                if isinstance(assigned_essay_id, bytes)
                else assigned_essay_id
            )
            self._logger.info(
                f"Successfully assigned content {text_storage_id} to slot {essay_id_str}"
            )
            return essay_id_str

    async def check_batch_completion(self, batch_id: str) -> bool:
        """
        Atomically check if batch is complete using comprehensive Redis state.

        A batch is complete when EITHER:
        1. No available slots remaining (all assigned or failed), OR
        2. Total processed (assigned + failed) >= expected count

        AND batch hasn't already been marked completed.
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
        pipe.scard(self._get_available_slots_key(batch_id))  # remaining slots
        pipe.llen(self._get_validation_failures_key(batch_id))  # failure count
        pipe.hlen(self._get_assignments_key(batch_id))  # assignment count
        pipe.hget(self._get_metadata_key(batch_id), "expected_count")  # expected count
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
        # REMOVED: The completion flag check was causing circular dependency
        # A batch can be complete regardless of whether it's been marked as completed

        total_processed = state["assigned_count"] + state["failure_count"]
        expected = state["expected_count"]
        no_slots_remaining = state["available_slots"] == 0

        # Batch complete if either all slots consumed OR all files processed
        return no_slots_remaining or (total_processed >= expected)

    async def mark_batch_completed_atomically(self, batch_id: str) -> bool:
        """
        Atomically mark batch as completed to prevent double-completion.

        Returns True if this call marked it completed, False if already completed.
        """
        # Use SET NX (set if not exists) for atomic completion flag
        result = await self._redis.set_if_not_exists(
            f"batch:{batch_id}:completed",
            "true",
            ttl_seconds=86400,  # 24 hour expiry
        )
        return result  # True if we set it, False if already existed

    async def get_available_slot_count(self, batch_id: str) -> int:
        """
        Get the number of available slots remaining for a batch.

        Args:
            batch_id: The batch identifier

        Returns:
            Number of available slots
        """
        try:
            slots_key = self._get_available_slots_key(batch_id)
            return await self._redis.scard(slots_key)
        except Exception as e:
            self._logger.error(
                f"Failed to get available slot count for {batch_id}: {e}", exc_info=True
            )
            raise

    async def get_batch_assignments(self, batch_id: str) -> dict[str, dict[str, Any]]:
        """
        Get all current slot assignments for a batch.

        Args:
            batch_id: The batch identifier

        Returns:
            Dictionary mapping essay_id to content metadata
        """
        try:
            assignments_key = self._get_assignments_key(batch_id)
            assignments_data = await self._redis.hgetall(assignments_key)

            # Parse JSON metadata for each assignment
            assignments = {}
            for essay_id, metadata_json in assignments_data.items():
                try:
                    assignments[essay_id] = json.loads(metadata_json)
                except json.JSONDecodeError as e:
                    self._logger.warning(
                        f"Failed to parse assignment metadata for {essay_id} "
                        f"in batch {batch_id}: {e}"
                    )
                    # Skip corrupted entries rather than failing entirely
                    continue

            return assignments

        except Exception as e:
            self._logger.error(
                f"Failed to get batch assignments for {batch_id}: {e}", exc_info=True
            )
            raise

    async def get_batch_metadata(self, batch_id: str) -> dict[str, Any] | None:
        """
        Get batch metadata from Redis.

        Args:
            batch_id: The batch identifier

        Returns:
            Batch metadata dictionary or None if batch not found
        """
        try:
            metadata_key = self._get_metadata_key(batch_id)
            metadata_data = await self._redis.hgetall(metadata_key)

            if not metadata_data:
                return None

            # Parse metadata fields back to appropriate types
            metadata = {}
            for field, value_str in metadata_data.items():
                # Try to parse JSON first (for complex types)
                try:
                    metadata[field] = json.loads(value_str)
                except json.JSONDecodeError:
                    # Fall back to string value
                    metadata[field] = value_str

            return metadata

        except Exception as e:
            self._logger.error(f"Failed to get batch metadata for {batch_id}: {e}", exc_info=True)
            raise

    async def get_batch_status(self, batch_id: str) -> dict[str, Any] | None:
        """
        Get comprehensive batch status from Redis.

        Args:
            batch_id: The batch identifier

        Returns:
            Status dictionary with slots, assignments, and metadata or None if not found
        """
        try:
            # Get batch metadata first to check existence
            metadata = await self.get_batch_metadata(batch_id)
            if metadata is None:
                return None

            # Get slot counts and assignments
            slots_key = self._get_available_slots_key(batch_id)
            assignments_key = self._get_assignments_key(batch_id)

            available_count = await self._redis.scard(slots_key)
            assignment_count = await self._redis.hlen(assignments_key)
            assignments = await self.get_batch_assignments(batch_id)

            # Check if timeout marker still exists
            timeout_key = self._get_timeout_key(batch_id)
            timeout_exists = await self._redis.get(timeout_key) is not None

            return {
                "batch_id": batch_id,
                "available_slots": available_count,
                "assigned_slots": assignment_count,
                "total_slots": available_count + assignment_count,
                "is_complete": available_count == 0,
                "has_timeout": timeout_exists,
                "assignments": assignments,
                "metadata": metadata,
            }

        except Exception as e:
            self._logger.error(f"Failed to get batch status for {batch_id}: {e}", exc_info=True)
            raise

    async def cleanup_batch(self, batch_id: str) -> None:
        """
        Clean up all Redis keys for a completed batch.

        Args:
            batch_id: The batch identifier
        """
        try:
            keys_to_delete = [
                self._get_available_slots_key(batch_id),
                self._get_assignments_key(batch_id),
                self._get_metadata_key(batch_id),
                self._get_timeout_key(batch_id),
                self._get_content_assignments_key(batch_id),  # Clean up content deduplication data
                self._get_validation_failures_key(batch_id),  # Clean up validation failures
                self._get_pending_failures_key(batch_id),  # Clean up any remaining pending failures
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
        """
        try:
            # Get final status before cleanup
            final_status = await self.get_batch_status(batch_id)

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

    async def get_assigned_count(self, batch_id: str) -> int:
        """
        Get count of assigned slots for a batch.

        Args:
            batch_id: The batch identifier

        Returns:
            Number of assigned slots
        """
        try:
            assignments_key = self._get_assignments_key(batch_id)
            count = await self._redis.hlen(assignments_key)
            return count or 0

        except Exception as e:
            self._logger.error(
                f"Failed to get assigned count for batch {batch_id}: {e}", exc_info=True
            )
            raise

    async def get_assigned_essays(self, batch_id: str) -> list[dict[str, Any]]:
        """
        Get all assigned essay metadata for a batch.

        Args:
            batch_id: The batch identifier

        Returns:
            List of essay metadata dictionaries with internal_essay_id included
        """
        try:
            assignments = await self.get_batch_assignments(batch_id)

            # Add internal_essay_id to each assignment metadata
            essays = []
            for essay_id, metadata in assignments.items():
                essay_data = metadata.copy()
                essay_data["internal_essay_id"] = essay_id
                essays.append(essay_data)

            return essays

        except Exception as e:
            self._logger.error(
                f"Failed to get assigned essays for batch {batch_id}: {e}", exc_info=True
            )
            raise

    async def get_missing_slots(self, batch_id: str) -> list[str]:
        """
        Get list of unassigned slot IDs for a batch.

        Args:
            batch_id: The batch identifier

        Returns:
            List of available (unassigned) essay IDs
        """
        try:
            slots_key = self._get_available_slots_key(batch_id)
            slots = await self._redis.smembers(slots_key)
            return list(slots) if slots else []

        except Exception as e:
            self._logger.error(
                f"Failed to get missing slots for batch {batch_id}: {e}", exc_info=True
            )
            raise

    def _get_validation_failures_key(self, batch_id: str) -> str:
        """Get Redis key for validation failures list."""
        return f"batch:{batch_id}:validation_failures"

    def _get_pending_failures_key(self, batch_id: str) -> str:
        """Get Redis key for pending validation failures that arrived before batch registration."""
        return f"batch:{batch_id}:pending_failures"

    async def track_validation_failure(self, batch_id: str, failure: dict[str, Any]) -> None:
        """
        Track a validation failure for a batch atomically.

        If batch doesn't exist yet, stores the failure as pending to be processed
        when the batch is registered. This handles race conditions where validation
        failures arrive before batch registration.

        Args:
            batch_id: The batch identifier
            failure: Validation failure data (will be JSON-encoded)
        """
        try:
            # First check if batch exists
            batch_status = await self.get_batch_status(batch_id)
            failure_json = json.dumps(failure)

            if batch_status is None:
                # Batch not registered yet - store as pending failure
                pending_key = self._get_pending_failures_key(batch_id)
                await self._redis.rpush(pending_key, failure_json)
                # Set TTL on pending failures to prevent memory leak
                await self._redis.expire(pending_key, 86400)  # 24 hours

                self._logger.info(
                    f"Stored pending validation failure for unregistered batch {batch_id}: "
                    f"{failure.get('original_file_name', 'unknown')}"
                )
                return

            # Batch exists - process normally
            failures_key = self._get_validation_failures_key(batch_id)
            slots_key = self._get_available_slots_key(batch_id)

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
            timeout_key = self._get_timeout_key(batch_id)
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
        """
        try:
            failures_key = self._get_validation_failures_key(batch_id)
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
        """
        try:
            failures_key = self._get_validation_failures_key(batch_id)
            count = await self._redis.llen(failures_key)
            return count or 0

        except Exception as e:
            self._logger.error(
                f"Failed to get validation failure count for batch {batch_id}: {e}", exc_info=True
            )
            raise

    async def list_active_batch_ids(self) -> list[str]:
        """
        List all active batch IDs by scanning Redis metadata keys.

        Returns:
            List of active batch IDs
        """
        try:
            metadata_keys = await self._redis.scan_pattern("batch:*:metadata")
            batch_ids = []

            for key in metadata_keys:
                # Extract batch_id from key pattern: batch:{batch_id}:metadata
                key_parts = key.split(":")
                if len(key_parts) >= 3 and key_parts[0] == "batch" and key_parts[-1] == "metadata":
                    batch_id = ":".join(key_parts[1:-1])  # Handle batch_ids that contain colons
                    batch_ids.append(batch_id)

            self._logger.debug(f"Found {len(batch_ids)} active batches in Redis")
            return batch_ids

        except Exception as e:
            self._logger.error(f"Failed to list active batch IDs: {e}", exc_info=True)
            raise

    async def get_essay_id_for_content(self, batch_id: str, text_storage_id: str) -> str | None:
        """
        Get the essay ID assigned to a specific text_storage_id.

        Args:
            batch_id: The batch identifier
            text_storage_id: The text storage ID to look up

        Returns:
            The essay ID if content is assigned, None otherwise
        """
        try:
            content_assignments_key = self._get_content_assignments_key(batch_id)
            essay_id = await self._redis.hget(content_assignments_key, text_storage_id)
            return essay_id
        except Exception as e:
            self._logger.error(
                f"Failed to get essay ID for content {text_storage_id} in batch {batch_id}: {e}",
                exc_info=True,
            )
            raise

    async def find_batch_for_essay(self, essay_id: str) -> tuple[str, str] | None:
        """
        Find the batch and user_id for a given essay by scanning batch assignments.

        Args:
            essay_id: The internal essay ID to search for

        Returns:
            Tuple of (batch_id, user_id) if found, None otherwise
        """
        try:
            # Get all active batch IDs
            batch_ids = await self.list_active_batch_ids()

            # Search through each batch's assignments
            for batch_id in batch_ids:
                assignments_key = self._get_assignments_key(batch_id)

                # Check if this essay_id exists in this batch's assignments
                assignment_exists = await self._redis.hexists(assignments_key, essay_id)

                if assignment_exists:
                    # Get the batch metadata to extract user_id
                    metadata = await self.get_batch_metadata(batch_id)
                    if metadata and "user_id" in metadata:
                        user_id = metadata["user_id"]
                        self._logger.debug(
                            f"Found essay {essay_id} in batch {batch_id} for user {user_id}"
                        )
                        return (batch_id, user_id)
                    else:
                        self._logger.warning(
                            f"Found essay {essay_id} in batch {batch_id} but no user_id in metadata"
                        )

            # Essay not found in any batch
            self._logger.debug(f"Essay {essay_id} not found in any active batch")
            return None

        except Exception as e:
            self._logger.error(f"Failed to find batch for essay {essay_id}: {e}", exc_info=True)
            raise
