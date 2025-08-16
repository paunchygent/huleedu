"""
Redis-cached batch state repository implementation for BCS.

Implements Redis cache + PostgreSQL persistence pattern for essay processing
state management, optimized for frequent BOS polling during pipeline resolution.

Follows established patterns from ELS state_store.py and BOS postgres repository.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import UTC, datetime
from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from services.batch_conductor_service.protocols import BatchStateRepositoryProtocol

logger = create_service_logger("bcs.batch_state_repository")


class RedisCachedBatchStateRepositoryImpl(BatchStateRepositoryProtocol):
    """
    High-performance essay processing state with Redis cache + PostgreSQL persistence.

    Cache-aside pattern optimized for BOS frequent polling during pipeline resolution.
    Redis TTL: 7 days (covers typical batch processing timeframes)
    PostgreSQL: Permanent historical record for audit and reprocessing scenarios
    """

    def __init__(
        self,
        redis_client: AtomicRedisClientProtocol,
        postgres_repository: BatchStateRepositoryProtocol | None = None,
    ):
        self.redis_client = redis_client
        self.postgres_repository = postgres_repository
        self.redis_ttl = 7 * 24 * 60 * 60  # 7 days in seconds

    async def record_essay_step_completion(
        self, batch_id: str, essay_id: str, step_name: str, metadata: dict | None = None
    ) -> bool:
        """
        Record completion of a processing step for an essay using atomic operations.

        Uses WATCH/MULTI/EXEC pattern with exponential backoff retries for race condition safety.
        Falls back to non-atomic operation if atomic retries are exhausted.
        """
        # Try atomic operation first (up to 5 retries as per task spec)
        atomic_success = await self._atomic_record_essay_step_completion(
            batch_id, essay_id, step_name, metadata
        )

        if atomic_success:
            return True

        # Fallback to original non-atomic operation if atomic fails
        logger.warning(
            f"Atomic operation failed, falling back to non-atomic for essay "
            f"batch {batch_id} essay {essay_id} step {step_name}",
            extra={"batch_id": batch_id, "essay_id": essay_id, "step_name": step_name},
        )
        return await self._non_atomic_record_essay_step_completion(
            batch_id, essay_id, step_name, metadata
        )

    async def _atomic_record_essay_step_completion(
        self, batch_id: str, essay_id: str, step_name: str, metadata: dict | None = None
    ) -> bool:
        """
        Atomic version using WATCH/MULTI/EXEC pattern with exponential backoff.

        Returns True if successful, False if all retries exhausted.
        """
        essay_key = f"bcs:essay_state:{batch_id}:{essay_id}"
        batch_summary_key = f"bcs:batch_summary:{batch_id}"

        max_retries = 5
        base_delay = 0.01  # 10ms base delay

        for attempt in range(max_retries):
            try:
                # Get current essay state first (before creating pipeline)
                essay_state = await self._get_essay_state_from_redis(essay_key)

                # Check if step already completed (idempotency)
                if step_name in essay_state["completed_steps"]:
                    logger.debug(
                        f"Step {step_name} already completed for essay {essay_id}, skipping",
                        extra={"batch_id": batch_id, "essay_id": essay_id, "step_name": step_name},
                    )
                    return True

                # Create transaction pipeline with watched keys
                pipeline = await self.redis_client.create_transaction_pipeline(essay_key)

                # Prepare updated state
                essay_state["completed_steps"].add(step_name)
                essay_state["step_metadata"][step_name] = metadata or {}
                essay_state["last_updated"] = self._get_current_timestamp()

                # Start transaction
                pipeline.multi()

                # Queue commands in transaction - no await on pipeline methods
                serializable_data = self._make_json_serializable(essay_state)
                json_str = json.dumps(serializable_data)

                # Queue the setex operation (no await)
                pipeline.setex(essay_key, self.redis_ttl, json_str)
                # Queue the delete operation (no await)
                pipeline.delete(batch_summary_key)

                # Execute transaction
                result = await pipeline.execute()

                if result is not None:
                    # Transaction succeeded
                    logger.info(
                        f"Atomically recorded completion: "
                        f"batch={batch_id}, essay={essay_id}, step={step_name}",
                        extra={
                            "batch_id": batch_id,
                            "essay_id": essay_id,
                            "step_name": step_name,
                            "attempt": attempt + 1,
                        },
                    )

                    # Persist to PostgreSQL if available
                    if self.postgres_repository:
                        try:
                            await self.postgres_repository.record_essay_step_completion(
                                batch_id, essay_id, step_name, metadata
                            )
                        except Exception as e:
                            logger.warning(
                                f"PostgreSQL persistence failed (continuing with Redis): {e}"
                            )

                    return True
                else:
                    # Transaction was discarded (watched key changed)
                    logger.debug(
                        f"Atomic transaction discarded "
                        f"(key changed), attempt {attempt + 1}/{max_retries}",
                        extra={"batch_id": batch_id, "essay_id": essay_id, "step_name": step_name},
                    )

                    if attempt < max_retries - 1:
                        # Exponential backoff with jitter
                        delay = base_delay * (2**attempt) + random.uniform(0, 0.01)
                        await asyncio.sleep(delay)
                        continue

            except Exception as e:
                # Pipeline cleanup is automatic - no unwatch needed
                logger.error(
                    f"Error in atomic operation attempt {attempt + 1}/{max_retries}: {e}",
                    extra={"batch_id": batch_id, "essay_id": essay_id, "step_name": step_name},
                    exc_info=True,
                )

                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt) + random.uniform(0, 0.01)
                    await asyncio.sleep(delay)
                    continue

        logger.error(
            f"Atomic operation failed after {max_retries} attempts",
            extra={"batch_id": batch_id, "essay_id": essay_id, "step_name": step_name},
        )
        return False

    async def _non_atomic_record_essay_step_completion(
        self, batch_id: str, essay_id: str, step_name: str, metadata: dict | None = None
    ) -> bool:
        """
        Original non-atomic implementation as fallback.

        Updates both Redis cache (for performance) and PostgreSQL (for persistence).
        """
        try:
            # Build Redis keys
            essay_key = f"bcs:essay_state:{batch_id}:{essay_id}"
            batch_summary_key = f"bcs:batch_summary:{batch_id}"

            # Get current essay state from Redis
            essay_state = await self._get_essay_state_from_redis(essay_key)

            # Add the completed step
            essay_state["completed_steps"].add(step_name)
            essay_state["step_metadata"][step_name] = metadata or {}
            essay_state["last_updated"] = self._get_current_timestamp()

            # Update Redis with essay state (with TTL)
            success = await self._set_json_with_ttl(essay_key, essay_state, self.redis_ttl)
            if not success:
                logger.error(f"Failed to update Redis for essay {essay_id}")
                return False

            # Invalidate batch summary cache
            await self.redis_client.delete_key(batch_summary_key)

            # Persist to PostgreSQL if available
            if self.postgres_repository:
                try:
                    await self.postgres_repository.record_essay_step_completion(
                        batch_id, essay_id, step_name, metadata
                    )
                except Exception as e:
                    logger.warning(f"PostgreSQL persistence failed (continuing with Redis): {e}")

            logger.info(
                f"Recorded completion: batch={batch_id}, essay={essay_id}, step={step_name}",
                extra={"batch_id": batch_id, "essay_id": essay_id, "step_name": step_name},
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to record essay step completion: {e}",
                extra={"batch_id": batch_id, "essay_id": essay_id, "step_name": step_name},
                exc_info=True,
            )
            return False

    async def get_essay_completed_steps(self, batch_id: str, essay_id: str) -> set[str]:
        """Get completed steps for a specific essay."""
        essay_key = f"bcs:essay_state:{batch_id}:{essay_id}"
        essay_state = await self._get_essay_state_from_redis(essay_key)
        completed_steps = essay_state["completed_steps"]
        # Ensure we return a proper set of strings
        if isinstance(completed_steps, set):
            return completed_steps
        return set(completed_steps) if completed_steps else set()

    async def get_batch_completion_summary(self, batch_id: str) -> dict[str, dict[str, int]]:
        """
        Get batch completion summary with caching.

        Returns summary by step -> {completed: count, total: count}.
        Cached with shorter TTL since this data changes frequently during processing.
        """
        batch_summary_key = f"bcs:batch_summary:{batch_id}"

        # Try to get cached summary first
        cached_summary = await self._get_json_from_redis(batch_summary_key)
        if cached_summary:
            logger.debug(f"Batch summary cache hit for {batch_id}")
            return cached_summary

        # Build summary from individual essay states
        logger.debug(f"Building batch summary for {batch_id}")
        summary = await self._build_batch_summary(batch_id)

        # Cache the summary with shorter TTL (1 hour) since it changes during processing
        cache_ttl = 60 * 60  # 1 hour
        await self._set_json_with_ttl(batch_summary_key, summary, cache_ttl)

        return summary

    async def is_batch_step_complete(self, batch_id: str, step_name: str) -> bool:
        """
        Check if a processing step is complete for the entire batch.

        First tries Redis cache based on essay-level summary.
        Falls back to PostgreSQL phase_completions table if Redis data is missing.
        """
        try:
            # First try Redis-based summary approach
            summary = await self.get_batch_completion_summary(batch_id)

            if step_name in summary:
                step_summary = summary[step_name]
                redis_result = step_summary["completed"] == step_summary["total"]

                logger.debug(
                    f"Redis: Step {step_name} completion check for batch {batch_id}: {redis_result}",
                    extra={
                        "batch_id": batch_id,
                        "step_name": step_name,
                        "completed": step_summary["completed"],
                        "total": step_summary["total"],
                        "is_complete": redis_result,
                    },
                )
                return redis_result

            # Redis summary missing for this step - fall back to PostgreSQL
            if self.postgres_repository:
                logger.info(
                    f"Redis summary missing for step {step_name} in batch {batch_id}, falling back to PostgreSQL",
                    extra={"batch_id": batch_id, "step_name": step_name},
                )

                postgres_result = await self.postgres_repository.is_batch_step_complete(
                    batch_id, step_name
                )

                logger.info(
                    f"PostgreSQL fallback: Step {step_name} completion for batch {batch_id}: {postgres_result}",
                    extra={
                        "batch_id": batch_id,
                        "step_name": step_name,
                        "is_complete": postgres_result,
                    },
                )

                return postgres_result

            # No data in Redis and no PostgreSQL repository
            logger.debug(
                f"No completion data found for step {step_name} in batch {batch_id}",
                extra={"batch_id": batch_id, "step_name": step_name},
            )
            return False

        except Exception as e:
            logger.error(
                f"Failed to check step completion for batch {batch_id}, step {step_name}: {e}",
                extra={"batch_id": batch_id, "step_name": step_name, "error": str(e)},
                exc_info=True,
            )

            # Try PostgreSQL as last resort
            if self.postgres_repository:
                try:
                    return await self.postgres_repository.is_batch_step_complete(
                        batch_id, step_name
                    )
                except Exception:
                    pass

            return False

    async def _get_essay_state_from_redis(self, essay_key: str) -> dict[str, Any]:
        """Get essay state from Redis, returning default state if not found."""
        essay_data = await self._get_json_from_redis(essay_key)

        if essay_data is None:
            # Return default state for new essay
            return {
                "completed_steps": set(),
                "step_metadata": {},
                "created_at": self._get_current_timestamp(),
                "last_updated": self._get_current_timestamp(),
            }

        # Validate and convert completed_steps from list back to set
        completed_steps_raw = essay_data.get("completed_steps", [])

        # Handle malformed data gracefully
        if isinstance(completed_steps_raw, list):
            # Validate that all items in the list are strings
            if all(isinstance(item, str) for item in completed_steps_raw):
                essay_data["completed_steps"] = set(completed_steps_raw)
            else:
                # Log malformed list data for observability
                logger.warning(
                    f"Malformed completed_steps data found in Redis key {essay_key}: "
                    f"expected list of strings, got list with non-string items. "
                    f"Defaulting to empty set.",
                    extra={"redis_key": essay_key, "malformed_data": completed_steps_raw},
                )
                essay_data["completed_steps"] = set()
        elif isinstance(completed_steps_raw, str):
            # Log malformed data for observability
            logger.warning(
                f"Malformed completed_steps data found in Redis key {essay_key}: "
                f"expected list, got string. Defaulting to empty set.",
                extra={"redis_key": essay_key, "malformed_data": completed_steps_raw},
            )
            essay_data["completed_steps"] = set()
        else:
            # Log unknown data type
            logger.warning(
                f"Unknown completed_steps data type in Redis key {essay_key}: "
                f"expected list, got {type(completed_steps_raw)}. Defaulting to empty set.",
                extra={"redis_key": essay_key, "data_type": str(type(completed_steps_raw))},
            )
            essay_data["completed_steps"] = set()

        return essay_data

    async def _build_batch_summary(self, batch_id: str) -> dict[str, dict[str, int]]:
        """Build batch completion summary by scanning all essay states."""
        # Use Redis SCAN to find all essay keys for this batch
        pattern = f"bcs:essay_state:{batch_id}:*"
        essay_keys = await self.redis_client.scan_pattern(pattern)

        step_counts: dict[str, dict[str, int]] = {}

        for essay_key in essay_keys:
            essay_state = await self._get_essay_state_from_redis(essay_key)
            completed_steps = essay_state["completed_steps"]

            # Update counts for each step that has any progress
            all_possible_steps = set(completed_steps)
            # Note: We could extend this to include all known steps from configuration

            for step in all_possible_steps:
                if step not in step_counts:
                    step_counts[step] = {"completed": 0, "total": 0}

                step_counts[step]["total"] += 1
                if step in completed_steps:
                    step_counts[step]["completed"] += 1

        return step_counts

    async def _get_json_from_redis(self, key: str) -> dict[str, Any] | None:
        """Get and deserialize JSON data from Redis."""
        try:
            data = await self.redis_client.get(key)
            if data is None:
                return None

            if isinstance(data, bytes):
                data = data.decode("utf-8")

            parsed_data = json.loads(data)
            # Ensure we return a proper dict or None
            return parsed_data if isinstance(parsed_data, dict) else None
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to deserialize Redis data for key {key}: {e}")
            return None

    async def _set_json_with_ttl(self, key: str, data: dict[str, Any], ttl_seconds: int) -> bool:
        """Serialize and store JSON data in Redis with TTL."""
        try:
            serializable_data = self._make_json_serializable(data)
            json_str = json.dumps(serializable_data)
            return await self.redis_client.setex(key, ttl_seconds, json_str)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize data for Redis key {key}: {e}")
            return False

    def _make_json_serializable(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert sets to lists for JSON serialization."""
        result = {}
        for key, value in data.items():
            if isinstance(value, set):
                result[key] = list(value)
            else:
                result[key] = value
        return result

    def _get_current_timestamp(self) -> str:
        """Get current UTC timestamp as ISO string."""
        return datetime.now(UTC).isoformat()

    async def record_batch_phase_completion(
        self, batch_id: str, phase_name: str, completed: bool
    ) -> bool:
        """
        Record phase completion status using cache-aside pattern.

        Stores in Redis for fast lookups (7-day TTL) and persists to PostgreSQL
        for permanent storage. This enables dependency resolution even weeks/months
        after a phase completed.

        Args:
            batch_id: Batch identifier
            phase_name: Name of the completed phase
            completed: Whether the phase completed successfully

        Returns:
            True if recorded successfully, False otherwise
        """
        try:
            key = f"bcs:batch:{batch_id}:phases"
            field = phase_name
            value = "completed" if completed else "failed"

            # Store phase completion status in Redis for fast lookups
            await self.redis_client.hset(key, field, value)

            # Set TTL to 7 days for Redis cache
            await self.redis_client.expire(key, self.redis_ttl)

            # CRITICAL: Also persist to PostgreSQL for permanent record
            if self.postgres_repository:
                try:
                    await self.postgres_repository.record_batch_phase_completion(
                        batch_id, phase_name, completed
                    )
                    logger.info(
                        f"Recorded phase {phase_name} as {value} for batch {batch_id} "
                        f"(Redis cache + PostgreSQL permanent)",
                        extra={
                            "batch_id": batch_id,
                            "phase_name": phase_name,
                            "completed": completed,
                        },
                    )
                except Exception as pg_error:
                    # Log PostgreSQL failure but don't fail the operation
                    # Redis cache is sufficient for immediate needs
                    logger.warning(
                        f"PostgreSQL persistence failed for phase completion "
                        f"(continuing with Redis only): {pg_error}",
                        extra={"batch_id": batch_id, "phase_name": phase_name},
                    )
            else:
                logger.info(
                    f"Cached phase {phase_name} as {value} for batch {batch_id} in Redis only",
                    extra={
                        "batch_id": batch_id,
                        "phase_name": phase_name,
                        "completed": completed,
                    },
                )

            return True

        except Exception as e:
            logger.error(
                f"Failed to record phase completion for batch {batch_id}: {e}",
                extra={"batch_id": batch_id, "phase_name": phase_name},
                exc_info=True,
            )
            return False

    async def get_completed_phases(self, batch_id: str) -> set[str]:
        """
        Get all completed phases for a batch, with PostgreSQL fallback.

        First checks Redis cache, then falls back to PostgreSQL if needed.
        If PostgreSQL has data but Redis doesn't, repopulates Redis cache.

        Args:
            batch_id: Batch identifier

        Returns:
            Set of phase names that have completed successfully
        """
        try:
            key = f"bcs:batch:{batch_id}:phases"

            # First try Redis
            redis_phases = await self.redis_client.hgetall(key)

            if redis_phases:
                # Parse Redis data - only return phases marked as completed
                completed_phases = {
                    phase for phase, status in redis_phases.items() if status == "completed"
                }

                logger.debug(
                    f"Retrieved {len(completed_phases)} completed phases from Redis for batch {batch_id}",
                    extra={"batch_id": batch_id, "phase_count": len(completed_phases)},
                )
                return completed_phases

            # Redis miss - try PostgreSQL
            if self.postgres_repository:
                logger.info(
                    f"Redis cache miss for batch {batch_id}, querying PostgreSQL",
                    extra={"batch_id": batch_id},
                )

                # Get from PostgreSQL
                completed_phases = await self.postgres_repository.get_completed_phases(batch_id)

                if completed_phases:
                    # Repopulate Redis cache for faster future lookups
                    for phase in completed_phases:
                        await self.redis_client.hset(key, phase, "completed")
                    await self.redis_client.expire(key, self.redis_ttl)

                    logger.info(
                        f"Repopulated Redis cache with {len(completed_phases)} phases from PostgreSQL "
                        f"for batch {batch_id}",
                        extra={
                            "batch_id": batch_id,
                            "phase_count": len(completed_phases),
                        },
                    )

                return completed_phases

            # No data in either Redis or PostgreSQL
            return set()

        except Exception as e:
            logger.error(
                f"Failed to get completed phases for batch {batch_id}: {e}",
                extra={"batch_id": batch_id},
                exc_info=True,
            )

            # Try PostgreSQL as last resort
            if self.postgres_repository:
                try:
                    return await self.postgres_repository.get_completed_phases(batch_id)
                except Exception:
                    pass

            return set()

    async def clear_batch_pipeline_state(self, batch_id: str) -> bool:
        """
        Clear Redis cache entries for batch pipeline state.

        This clears the Redis cache when a pipeline completes to prevent memory bloat.
        The permanent records in PostgreSQL are NOT affected - they remain forever
        for dependency resolution.

        Args:
            batch_id: Batch identifier

        Returns:
            True if cleared successfully, False otherwise
        """
        try:
            key = f"bcs:batch:{batch_id}:phases"

            # Clear Redis cache for this batch's phases
            result = await self.redis_client.delete(key)

            # Also notify PostgreSQL (even though it's a no-op there)
            if self.postgres_repository:
                await self.postgres_repository.clear_batch_pipeline_state(batch_id)

            logger.info(
                f"Cleared Redis cache for batch {batch_id} pipeline state (deleted {result} keys). "
                f"PostgreSQL records retained permanently.",
                extra={"batch_id": batch_id, "keys_deleted": result},
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to clear Redis cache for batch {batch_id}: {e}",
                extra={"batch_id": batch_id},
                exc_info=True,
            )
            return False
