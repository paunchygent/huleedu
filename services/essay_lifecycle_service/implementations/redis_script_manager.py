"""
Redis script management and key generation for batch coordination.

Centralizes Lua scripts, script loading, and Redis key naming conventions
for the distributed batch coordination system.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol

logger = create_service_logger(__name__)


# -----------------------------------------------------------------------------
# ATOMIC SLOT ASSIGNMENT LUA SCRIPT
# -----------------------------------------------------------------------------
# This script performs idempotent and atomic slot assignment.
#
# Logic:
# 1. Idempotency Check: Checks if the content (text_storage_id) has already
#    been assigned a slot. If so, it returns the existing essay_id.
# 2. Atomic Slot Pop: If not already assigned, it atomically pops a slot from
#    the available_slots set using SPOP.
# 3. Handle No Slots: If SPOP returns nil (no slots available), the script
#    returns nil immediately.
# 4. Atomic Assignment: If a slot is acquired, it performs two HSET operations:
#    - Maps the content_id -> essay_id for future idempotency checks.
#    - Maps the essay_id -> content_metadata for data retrieval.
# 5. Return Value: Returns the assigned essay_id on success.
#
# KEYS[1]: content_assignments_key (e.g., batch:{id}:content_assignments) HASH
# KEYS[2]: available_slots_key (e.g., batch:{id}:available_slots) SET
# KEYS[3]: assignments_key (e.g., batch:{id}:assignments) HASH
#
# ARGV[1]: text_storage_id
# ARGV[2]: content_metadata_json
# -----------------------------------------------------------------------------
ATOMIC_ASSIGN_SCRIPT = """
local content_assignments_key = KEYS[1]
local available_slots_key = KEYS[2]
local assignments_key = KEYS[3]

local text_storage_id = ARGV[1]
local content_metadata_json = ARGV[2]

-- 1. Idempotency Check: See if this content is already assigned a slot
local existing_essay_id = redis.call('HGET', content_assignments_key, text_storage_id)
if existing_essay_id then
    return existing_essay_id
end

-- 2. Atomically get an available slot
local assigned_essay_id = redis.call('SPOP', available_slots_key)

-- 3. If no slots are available, return nil
if not assigned_essay_id then
    return nil
end

-- 4. A slot was found, so perform the assignments
redis.call('HSET', content_assignments_key, text_storage_id, assigned_essay_id)
redis.call('HSET', assignments_key, assigned_essay_id, content_metadata_json)

-- 5. Return the assigned slot ID
return assigned_essay_id
"""


# -----------------------------------------------------------------------------
# ATOMIC SLOT RETURN LUA SCRIPT
# -----------------------------------------------------------------------------
# This script atomically returns a previously assigned slot to the available pool.
#
# Use Case: This is for POST-ASSIGNMENT rollback scenarios where a slot was
# successfully assigned but needs to be returned due to downstream processing
# failures. NOT for pre-assignment validation failures (which use SPOP).
#
# KEYS[1]: content_assignments_key (e.g., batch:{id}:content_assignments) HASH
# KEYS[2]: available_slots_key (e.g., batch:{id}:available_slots) SET
# KEYS[3]: assignments_key (e.g., batch:{id}:assignments) HASH
#
# ARGV[1]: text_storage_id
# -----------------------------------------------------------------------------
ATOMIC_RETURN_SCRIPT = """
local content_assignments_key = KEYS[1]
local available_slots_key = KEYS[2]
local assignments_key = KEYS[3]

local text_storage_id = ARGV[1]

-- Get current assignment
local essay_id = redis.call('HGET', content_assignments_key, text_storage_id)
if not essay_id then
    return nil
end

-- Remove assignment
redis.call('HDEL', content_assignments_key, text_storage_id)
redis.call('HDEL', assignments_key, essay_id)

-- Return slot to available set
redis.call('SADD', available_slots_key, essay_id)

return essay_id
"""


class RedisScriptManager:
    """
    Manages Lua scripts and Redis key naming for batch coordination.

    Handles script loading, caching, and provides consistent key naming
    across all batch coordination operations.
    """

    def __init__(self, redis_client: AtomicRedisClientProtocol) -> None:
        self._redis = redis_client
        self._logger = logger

        # Script loading state with concurrency protection
        self._script_load_lock = asyncio.Lock()
        self._atomic_assign_script_sha: str | None = None
        self._atomic_return_script_sha: str | None = None

    # Redis Key Generation Methods
    def get_available_slots_key(self, batch_id: str) -> str:
        """Get Redis key for available slots set."""
        return f"batch:{batch_id}:available_slots"

    def get_assignments_key(self, batch_id: str) -> str:
        """Get Redis key for assignments hash."""
        return f"batch:{batch_id}:assignments"

    def get_metadata_key(self, batch_id: str) -> str:
        """Get Redis key for batch metadata hash."""
        return f"batch:{batch_id}:metadata"

    def get_timeout_key(self, batch_id: str) -> str:
        """Get Redis key for batch timeout tracking."""
        return f"batch:{batch_id}:timeout"

    def get_content_assignments_key(self, batch_id: str) -> str:
        """Get Redis key for content assignments hash (text_storage_id -> essay_id mapping)."""
        return f"batch:{batch_id}:content_assignments"

    def get_validation_failures_key(self, batch_id: str) -> str:
        """Get Redis key for validation failures list."""
        return f"batch:{batch_id}:validation_failures"

    def get_pending_failures_key(self, batch_id: str) -> str:
        """Get Redis key for pending validation failures that arrived before batch registration."""
        return f"batch:{batch_id}:pending_failures"

    # Script Loading and Management
    async def ensure_scripts_loaded(self) -> None:
        """Load Lua scripts if not already loaded, protected by a lock."""
        if self._atomic_assign_script_sha and self._atomic_return_script_sha:
            return

        async with self._script_load_lock:
            # Double-check inside the lock to prevent re-loading
            if self._atomic_assign_script_sha is None:
                self._atomic_assign_script_sha = await self._redis.register_script(
                    ATOMIC_ASSIGN_SCRIPT
                )
                self._logger.info("Loaded atomic slot assignment script")

            if self._atomic_return_script_sha is None:
                self._atomic_return_script_sha = await self._redis.register_script(
                    ATOMIC_RETURN_SCRIPT
                )
                self._logger.info("Loaded atomic slot return script")

    async def execute_assign_script(self, keys: list[str], args: list[str]) -> str | None:
        """Execute the atomic assignment script."""
        await self.ensure_scripts_loaded()
        assert self._atomic_assign_script_sha is not None, "Script SHA must be loaded"
        result = await self._redis.execute_script(self._atomic_assign_script_sha, keys, args)
        return result if result is None or isinstance(result, str) else str(result)

    async def execute_return_script(self, keys: list[str], args: list[str]) -> str | None:
        """Execute the atomic return script."""
        await self.ensure_scripts_loaded()
        assert self._atomic_return_script_sha is not None, "Script SHA must be loaded"
        result = await self._redis.execute_script(self._atomic_return_script_sha, keys, args)
        return result if result is None or isinstance(result, str) else str(result)
