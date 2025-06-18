"""
Batch state repository implementation for BCS.

Implements Redis cache + PostgreSQL persistence pattern for essay processing
state management, optimized for frequent BOS polling during pipeline resolution.

Follows established patterns from ELS state_store.py and BOS postgres repository.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol
from services.batch_conductor_service.protocols import BatchStateRepositoryProtocol

if TYPE_CHECKING:
    pass  # PostgreSQLBatchStateRepositoryImpl defined later in this file

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
        redis_client: RedisClientProtocol,
        postgres_repository: BatchStateRepositoryProtocol | None = None,
    ):
        self.redis_client = redis_client
        self.postgres_repository = postgres_repository
        self.redis_ttl = 7 * 24 * 60 * 60  # 7 days in seconds

    async def record_essay_step_completion(
        self, batch_id: str, essay_id: str, step_name: str, metadata: dict | None = None
    ) -> bool:
        """
        Record completion of a processing step for an essay.

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

            # Update Redis cache with extended JSON
            success = await self._set_json_with_ttl(essay_key, essay_state, self.redis_ttl)
            if not success:
                logger.error(f"Failed to update Redis cache for essay {essay_id} step {step_name}")
                return False

            # Invalidate batch summary cache (will be rebuilt on next query)
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
                extra={"batch_id": batch_id, "essay_id": essay_id, "step_name": step_name}
            )
            return True

        except Exception as e:
            logger.error(f"Failed to record step completion: {e}", exc_info=True)
            return False

    async def get_essay_completed_steps(self, batch_id: str, essay_id: str) -> set[str]:
        """
        Get all completed processing steps for an essay.

        Cache-first approach with PostgreSQL fallback if cache miss.
        """
        try:
            essay_key = f"bcs:essay_state:{batch_id}:{essay_id}"

            # Try Redis cache first
            essay_state = await self._get_essay_state_from_redis(essay_key)
            completed_steps: set[str] = essay_state["completed_steps"]
            if completed_steps:
                return completed_steps

            # Cache miss - try PostgreSQL fallback
            if self.postgres_repository:
                try:
                    steps = await self.postgres_repository.get_essay_completed_steps(
                        batch_id, essay_id
                    )
                    # Warm cache for future queries
                    if steps:
                        essay_state["completed_steps"] = steps
                        await self._set_json_with_ttl(essay_key, essay_state, self.redis_ttl)
                    return steps
                except Exception as e:
                    logger.warning(f"PostgreSQL fallback failed: {e}")

            return set()

        except Exception as e:
            logger.error(f"Failed to get completed steps for essay {essay_id}: {e}", exc_info=True)
            return set()

    async def get_batch_completion_summary(self, batch_id: str) -> dict[str, dict[str, int]]:
        """
        Get completion summary for all essays in a batch.

        Returns dict mapping step_name -> {'completed': count, 'total': count}
        Cached for 5 minutes to optimize BOS polling performance.
        """
        try:
            summary_key = f"bcs:batch_summary:{batch_id}"

            # Try Redis cache first (5 minute TTL for batch summary)
            summary_json = await self._get_json_from_redis(summary_key)
            if summary_json:
                return summary_json

            # Cache miss - build summary from individual essay states
            summary = await self._build_batch_summary(batch_id)

            # Cache the summary with shorter TTL (5 minutes)
            await self._set_json_with_ttl(summary_key, summary, ttl_seconds=300)

            return summary

        except Exception as e:
            logger.error(f"Failed to get batch completion summary for {batch_id}: {e}", exc_info=True)
            return {}

    async def is_batch_step_complete(self, batch_id: str, step_name: str) -> bool:
        """
        Check if a processing step is complete for all essays in a batch.

        Uses cached batch summary for optimal performance.
        """
        try:
            summary = await self.get_batch_completion_summary(batch_id)
            step_data = summary.get(step_name, {"completed": 0, "total": 0})

            total_essays = step_data["total"]
            completed_essays = step_data["completed"]

            # Step is complete if all essays have completed it
            return total_essays > 0 and completed_essays == total_essays

        except Exception as e:
            logger.error(f"Failed to check batch step completion: {e}", exc_info=True)
            return False

    async def _get_essay_state_from_redis(self, essay_key: str) -> dict[str, Any]:
        """Get essay state from Redis, returning default structure if not found."""
        try:
            state_json = await self._get_json_from_redis(essay_key)
            if state_json:
                # Convert completed_steps list back to set
                state_json["completed_steps"] = set(state_json.get("completed_steps", []))
                return state_json
        except Exception as e:
            logger.warning(f"Failed to get essay state from Redis: {e}")

        # Return default structure
        return {
            "completed_steps": set(),
            "step_metadata": {},
            "created_at": self._get_current_timestamp(),
            "last_updated": self._get_current_timestamp(),
        }

    async def _build_batch_summary(self, batch_id: str) -> dict[str, dict[str, int]]:
        """Build batch completion summary from individual essay states."""
        try:
            # Note: This is a simplified implementation
            # In production, you might want to maintain a batch essay registry
            # For now, we'll build from known essays or use PostgreSQL

            if self.postgres_repository:
                return await self.postgres_repository.get_batch_completion_summary(batch_id)

            # Fallback: return empty summary if no PostgreSQL
            logger.warning(f"No PostgreSQL repository available for batch summary: {batch_id}")
            return {}

        except Exception as e:
            logger.error(f"Failed to build batch summary for {batch_id}: {e}", exc_info=True)
            return {}

    async def _get_json_from_redis(self, key: str) -> dict[str, Any] | None:
        """Get JSON data from Redis using string operations."""
        try:
            json_str = await self.redis_client.get(key)
            if json_str:
                data = json.loads(json_str)
                # Ensure we return the correct type
                return dict(data) if isinstance(data, dict) else None
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in Redis key {key}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to get JSON from Redis key {key}: {e}")
            return None

    async def _set_json_with_ttl(self, key: str, data: dict[str, Any], ttl_seconds: int) -> bool:
        """Set JSON data in Redis using string operations with TTL."""
        try:
            # Convert sets to lists for JSON serialization
            serializable_data = self._make_json_serializable(data)
            json_str = json.dumps(serializable_data)
            return await self.redis_client.setex(key, ttl_seconds, json_str)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to serialize data for Redis key {key}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Failed to set JSON in Redis key {key}: {e}", exc_info=True)
            return False

    def _make_json_serializable(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert data structure to be JSON serializable."""
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, set):
                result[key] = list(value)
            elif isinstance(value, dict):
                result[key] = self._make_json_serializable(value)
            else:
                result[key] = value
        return result

    def _get_current_timestamp(self) -> str:
        """Get current timestamp as ISO format string."""
        return datetime.now(UTC).isoformat()


class PostgreSQLBatchStateRepositoryImpl(BatchStateRepositoryProtocol):
    """
    PostgreSQL implementation for permanent batch state persistence.

    Used as fallback/persistence layer behind Redis cache.
    Follows BOS PostgreSQL patterns for schema and operations.
    """

    def __init__(self, database_url: str):
        self.database_url = database_url
        # Note: Implementation would follow BOS PostgreSQL patterns
        # with proper SQLAlchemy setup, connection pooling, etc.

    async def record_essay_step_completion(
        self, batch_id: str, essay_id: str, step_name: str, metadata: dict | None = None
    ) -> bool:
        """Record essay step completion in PostgreSQL."""
        # Implementation would use SQLAlchemy similar to BOS
        # with proper table schema for essay processing state
        return True  # Placeholder

    async def get_essay_completed_steps(self, batch_id: str, essay_id: str) -> set[str]:
        """Get completed steps from PostgreSQL."""
        # Implementation would query the essay_processing_state table
        return set()  # Placeholder

    async def get_batch_completion_summary(self, batch_id: str) -> dict[str, dict[str, int]]:
        """Get batch completion summary from PostgreSQL."""
        # Implementation would use aggregation queries
        return {}  # Placeholder

    async def is_batch_step_complete(self, batch_id: str, step_name: str) -> bool:
        """Check batch step completion from PostgreSQL."""
        summary = await self.get_batch_completion_summary(batch_id)
        step_data = summary.get(step_name, {"completed": 0, "total": 0})
        return step_data["total"] > 0 and step_data["completed"] == step_data["total"]
