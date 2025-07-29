"""
Redis batch query and discovery operations.

Handles all read-only operations for batch status, metadata, assignments,
and cross-batch discovery operations.
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


class RedisBatchQueries:
    """
    Provides read-only query operations for batch data in Redis.

    Handles batch status queries, metadata retrieval, assignment lookups,
    and cross-batch discovery operations.
    """

    def __init__(
        self, redis_client: AtomicRedisClientProtocol, script_manager: RedisScriptManager
    ) -> None:
        self._redis = redis_client
        self._script_manager = script_manager
        self._logger = logger

    async def get_batch_assignments(self, batch_id: str) -> dict[str, dict[str, Any]]:
        """
        Get all current slot assignments for a batch.

        Args:
            batch_id: The batch identifier

        Returns:
            Dictionary mapping essay_id to content metadata

        Raises:
            Exception: If Redis operation fails
        """
        try:
            assignments_key = self._script_manager.get_assignments_key(batch_id)
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

        Raises:
            Exception: If Redis operation fails
        """
        try:
            metadata_key = self._script_manager.get_metadata_key(batch_id)
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

        Raises:
            Exception: If Redis operation fails
        """
        try:
            # Get batch metadata first to check existence
            metadata = await self.get_batch_metadata(batch_id)
            if metadata is None:
                return None

            # Get slot counts and assignments
            slots_key = self._script_manager.get_available_slots_key(batch_id)
            assignments_key = self._script_manager.get_assignments_key(batch_id)

            available_count = await self._redis.scard(slots_key)
            assignment_count = await self._redis.hlen(assignments_key)
            assignments = await self.get_batch_assignments(batch_id)

            # Check if timeout marker still exists
            timeout_key = self._script_manager.get_timeout_key(batch_id)
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

    async def get_assigned_essays(self, batch_id: str) -> list[dict[str, Any]]:
        """
        Get all assigned essay metadata for a batch.

        Args:
            batch_id: The batch identifier

        Returns:
            List of essay metadata dictionaries with internal_essay_id included

        Raises:
            Exception: If Redis operation fails
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

        Raises:
            Exception: If Redis operation fails
        """
        try:
            slots_key = self._script_manager.get_available_slots_key(batch_id)
            slots = await self._redis.smembers(slots_key)
            return list(slots) if slots else []

        except Exception as e:
            self._logger.error(
                f"Failed to get missing slots for batch {batch_id}: {e}", exc_info=True
            )
            raise

    async def list_active_batch_ids(self) -> list[str]:
        """
        List all active batch IDs by scanning Redis metadata keys.

        Returns:
            List of active batch IDs

        Raises:
            Exception: If Redis operation fails
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

    async def find_batch_for_essay(self, essay_id: str) -> tuple[str, str] | None:
        """
        Find the batch and user_id for a given essay by scanning batch assignments.

        Args:
            essay_id: The internal essay ID to search for

        Returns:
            Tuple of (batch_id, user_id) if found, None otherwise

        Raises:
            Exception: If Redis operation fails
        """
        try:
            # Get all active batch IDs
            batch_ids = await self.list_active_batch_ids()

            # Search through each batch's assignments
            for batch_id in batch_ids:
                assignments_key = self._script_manager.get_assignments_key(batch_id)

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
