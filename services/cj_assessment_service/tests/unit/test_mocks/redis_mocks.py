"""Redis client mocks for CJ Assessment Service unit tests.

Provides mock implementations of RedisClientProtocol for testing
idempotency and caching patterns without requiring actual Redis connections.
"""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.protocols import RedisClientProtocol


class MockRedisClient(RedisClientProtocol):
    """Mock Redis client for idempotency testing."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []
        self.delete_calls: list[str] = []
        self.should_fail_set = False
        self.should_fail_delete = False

    async def set_if_not_exists(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Set a key only if it doesn't exist with optional TTL."""
        self.set_calls.append((key, str(value), ttl_seconds or 0))
        if self.should_fail_set:
            raise Exception("Redis connection failed")
        if key in self.keys:
            return False
        self.keys[key] = str(value)
        return True

    async def delete_key(self, key: str) -> int:
        """Delete a key from the mock Redis store."""
        self.delete_calls.append(key)
        if self.should_fail_delete:
            raise Exception("Redis connection failed")
        if key in self.keys:
            del self.keys[key]
            return 1
        return 0

    async def get(self, key: str) -> str | None:
        """Get a value from the mock Redis store."""
        if self.should_fail_set:  # Simulate full Redis outage
            raise Exception("Redis connection failed")
        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Set a key with TTL."""
        self.keys[key] = value
        return True

    async def ping(self) -> bool:
        """Mock PING operation required by RedisClientProtocol."""
        return True

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys from the mock Redis store."""
        count = 0
        for key in keys:
            self.delete_calls.append(key)
            if key in self.keys:
                del self.keys[key]
                count += 1
        return count
