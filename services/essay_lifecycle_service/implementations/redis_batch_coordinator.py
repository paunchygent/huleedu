"""
Redis-based batch coordinator for distributed slot assignment.

Replaces in-memory batch state management with atomic Redis operations
to enable horizontal scaling and eliminate race conditions in slot assignment.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.essay_lifecycle_service.config import Settings


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
        self._logger = create_service_logger("redis_batch_coordinator")
        self._default_timeout = 300  # 5 minutes default

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

    async def register_batch_slots(
        self, 
        batch_id: str, 
        essay_ids: list[str], 
        metadata: dict[str, Any],
        timeout_seconds: int | None = None
    ) -> None:
        """
        Initialize available slots for batch with metadata.
        
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
            # Use Redis pipeline for atomic batch initialization
            await self._redis.multi()

            # Initialize available slots as a Redis SET
            slots_key = self._get_available_slots_key(batch_id)
            await self._redis.sadd(slots_key, *essay_ids)

            # Store batch metadata as a Redis HASH
            metadata_key = self._get_metadata_key(batch_id)
            for field, value in metadata.items():
                # Convert values to strings for Redis storage
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value)
                elif isinstance(value, UUID):
                    value_str = str(value)
                elif isinstance(value, datetime):
                    value_str = value.isoformat()
                else:
                    value_str = str(value)
                await self._redis.hset(metadata_key, field, value_str)

            # Set TTL for automatic cleanup
            timeout_key = self._get_timeout_key(batch_id)
            await self._redis.setex(timeout_key, timeout, "timeout_marker")

            # Execute atomic transaction
            results = await self._redis.exec()
            
            if results is None:
                raise RuntimeError(f"Batch registration transaction failed for batch {batch_id}")

            self._logger.info(
                f"Registered batch {batch_id} with {len(essay_ids)} slots, "
                f"timeout: {timeout}s"
            )

        except Exception as e:
            await self._redis.unwatch()  # Clean up on error
            self._logger.error(
                f"Failed to register batch {batch_id}: {e}",
                exc_info=True
            )
            raise

    async def assign_slot_atomic(
        self, 
        batch_id: str, 
        content_metadata: dict[str, Any]
    ) -> str | None:
        """
        Atomically assign an available slot to content using Redis SPOP.
        
        Args:
            batch_id: The batch identifier
            content_metadata: Content metadata including text_storage_id, original_file_name
            
        Returns:
            The assigned internal essay ID if successful, None if no slots available
        """
        slots_key = self._get_available_slots_key(batch_id)
        assignments_key = self._get_assignments_key(batch_id)

        try:
            # Use Redis transaction with optimistic locking
            await self._redis.watch(slots_key, assignments_key)
            await self._redis.multi()

            # Atomically pop a slot from available set
            essay_id = await self._redis.spop(slots_key)
            
            if essay_id is None:
                # No slots available - abort transaction
                await self._redis.unwatch()
                self._logger.warning(f"No available slots for batch {batch_id}")
                return None

            # Store assignment metadata
            metadata_json = json.dumps(content_metadata)
            await self._redis.hset(assignments_key, essay_id, metadata_json)

            # Execute atomic transaction
            results = await self._redis.exec()
            
            if results is None:
                # Transaction was discarded due to key changes
                self._logger.warning(
                    f"Slot assignment transaction discarded for batch {batch_id} "
                    "(concurrent modification detected)"
                )
                return None

            self._logger.info(
                f"Assigned slot {essay_id} to content {content_metadata.get('text_storage_id')} "
                f"in batch {batch_id}"
            )
            return essay_id

        except Exception as e:
            await self._redis.unwatch()  # Clean up on error
            self._logger.error(
                f"Failed to assign slot for batch {batch_id}: {e}",
                exc_info=True
            )
            raise

    async def check_batch_completion(self, batch_id: str) -> bool:
        """
        Check if batch is complete using Redis state.
        
        A batch is complete when there are no remaining available slots.
        
        Args:
            batch_id: The batch identifier
            
        Returns:
            True if batch is complete (no available slots)
        """
        try:
            slots_key = self._get_available_slots_key(batch_id)
            available_count = await self._redis.scard(slots_key)
            
            is_complete = available_count == 0
            
            self._logger.debug(
                f"Batch {batch_id} completion check: {available_count} slots remaining, "
                f"complete: {is_complete}"
            )
            
            return is_complete

        except Exception as e:
            self._logger.error(
                f"Failed to check batch completion for {batch_id}: {e}",
                exc_info=True
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
                f"Failed to get batch assignments for {batch_id}: {e}",
                exc_info=True
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
            self._logger.error(
                f"Failed to get batch metadata for {batch_id}: {e}",
                exc_info=True
            )
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
            self._logger.error(
                f"Failed to get batch status for {batch_id}: {e}",
                exc_info=True
            )
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
            ]

            for key in keys_to_delete:
                await self._redis.delete_key(key)

            self._logger.info(f"Cleaned up Redis keys for completed batch {batch_id}")

        except Exception as e:
            self._logger.error(
                f"Failed to cleanup batch {batch_id}: {e}",
                exc_info=True
            )
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
            self._logger.error(
                f"Failed to handle timeout for batch {batch_id}: {e}",
                exc_info=True
            )
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
                f"Failed to get assigned count for batch {batch_id}: {e}",
                exc_info=True
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
                essay_data['internal_essay_id'] = essay_id
                essays.append(essay_data)
                
            return essays
            
        except Exception as e:
            self._logger.error(
                f"Failed to get assigned essays for batch {batch_id}: {e}",
                exc_info=True
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
                f"Failed to get missing slots for batch {batch_id}: {e}",
                exc_info=True
            )
            raise