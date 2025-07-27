"""
Unit tests for Redis Lua script functionality.

Tests the register_script and execute_script methods added to RedisClient
for atomic operations support.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from huleedu_service_libs.redis_client import RedisClient


class TestRedisLuaScripts:
    """Test Redis Lua script operations."""

    @pytest_asyncio.fixture
    async def redis_client(self):
        """Create a RedisClient instance with mocked Redis connection."""
        client = RedisClient(client_id="test-lua", redis_url="redis://localhost:6379")
        
        # Mock the underlying Redis client
        mock_redis = AsyncMock()
        client.client = mock_redis
        client._started = True
        
        yield client

    async def test_register_script_success(self, redis_client: RedisClient):
        """Test successful Lua script registration."""
        # Arrange
        test_script = """
        local key = KEYS[1]
        local value = ARGV[1]
        return redis.call('SET', key, value)
        """
        expected_sha = "a1b2c3d4e5f6"
        
        redis_client.client.script_load = AsyncMock(return_value=expected_sha)
        
        # Act
        result_sha = await redis_client.register_script(test_script)
        
        # Assert
        assert result_sha == expected_sha
        redis_client.client.script_load.assert_called_once_with(test_script)

    async def test_register_script_not_started(self):
        """Test script registration fails when client not started."""
        # Arrange
        client = RedisClient(client_id="test-lua", redis_url="redis://localhost:6379")
        client._started = False
        
        # Act & Assert
        with pytest.raises(RuntimeError, match="Redis client 'test-lua' is not running"):
            await client.register_script("test script")

    async def test_register_script_error(self, redis_client: RedisClient):
        """Test script registration handles Redis errors."""
        # Arrange
        test_script = "invalid script"
        redis_client.client.script_load = AsyncMock(side_effect=Exception("Script error"))
        
        # Act & Assert
        with pytest.raises(Exception, match="Script error"):
            await redis_client.register_script(test_script)

    async def test_execute_script_success(self, redis_client: RedisClient):
        """Test successful Lua script execution."""
        # Arrange
        test_sha = "a1b2c3d4e5f6"
        test_keys = ["test:key1", "test:key2"]
        test_args = ["value1", "value2"]
        expected_result = "OK"
        
        redis_client.client.evalsha = AsyncMock(return_value=expected_result)
        
        # Act
        result = await redis_client.execute_script(test_sha, test_keys, test_args)
        
        # Assert
        assert result == expected_result
        redis_client.client.evalsha.assert_called_once_with(
            test_sha, 2, "test:key1", "test:key2", "value1", "value2"
        )

    async def test_execute_script_not_started(self):
        """Test script execution fails when client not started."""
        # Arrange
        client = RedisClient(client_id="test-lua", redis_url="redis://localhost:6379")
        client._started = False
        
        # Act & Assert
        with pytest.raises(RuntimeError, match="Redis client 'test-lua' is not running"):
            await client.execute_script("sha123", [], [])

    async def test_execute_script_error(self, redis_client: RedisClient):
        """Test script execution handles Redis errors."""
        # Arrange
        test_sha = "invalid_sha"
        redis_client.client.evalsha = AsyncMock(side_effect=Exception("NOSCRIPT"))
        
        # Act & Assert
        with pytest.raises(Exception, match="NOSCRIPT"):
            await redis_client.execute_script(test_sha, [], [])

    async def test_execute_script_with_nil_result(self, redis_client: RedisClient):
        """Test script execution handles nil/None results."""
        # Arrange
        test_sha = "test_sha"
        redis_client.client.evalsha = AsyncMock(return_value=None)
        
        # Act
        result = await redis_client.execute_script(test_sha, ["key1"], ["arg1"])
        
        # Assert
        assert result is None

    async def test_atomic_operation_example(self, redis_client: RedisClient):
        """Test a complete atomic operation example."""
        # Arrange
        # Simulated atomic increment script
        increment_script = """
        local key = KEYS[1]
        local increment = tonumber(ARGV[1])
        local current = redis.call('GET', key)
        if current == false then
            current = 0
        else
            current = tonumber(current)
        end
        local new_value = current + increment
        redis.call('SET', key, new_value)
        return new_value
        """
        
        script_sha = "increment_sha"
        redis_client.client.script_load = AsyncMock(return_value=script_sha)
        redis_client.client.evalsha = AsyncMock(return_value=5)
        
        # Act
        # Register script
        sha = await redis_client.register_script(increment_script)
        
        # Execute script
        result = await redis_client.execute_script(sha, ["counter:1"], ["5"])
        
        # Assert
        assert sha == script_sha
        assert result == 5
        redis_client.client.script_load.assert_called_once_with(increment_script)
        redis_client.client.evalsha.assert_called_once_with(
            script_sha, 1, "counter:1", "5"
        )


class TestLuaScriptIntegration:
    """Integration tests with actual Redis if available."""

    @pytest.mark.integration
    @pytest_asyncio.fixture
    async def real_redis_client(self):
        """Create a real Redis client for integration tests."""
        client = RedisClient(client_id="test-lua-integration")
        try:
            await client.start()
            yield client
        finally:
            await client.stop()

    @pytest.mark.integration
    async def test_real_lua_script_execution(self, real_redis_client: RedisClient):
        """Test Lua script execution with real Redis."""
        # Simple test script that sets a key
        test_script = """
        local key = KEYS[1]
        local value = ARGV[1]
        redis.call('SET', key, value)
        return redis.call('GET', key)
        """
        
        # Register script
        sha = await real_redis_client.register_script(test_script)
        assert sha is not None
        assert len(sha) == 40  # SHA1 hash length
        
        # Execute script
        test_key = "test:lua:key"
        test_value = "Hello from Lua!"
        result = await real_redis_client.execute_script(sha, [test_key], [test_value])
        
        assert result == test_value
        
        # Verify the value was actually set
        stored_value = await real_redis_client.get(test_key)
        assert stored_value == test_value
        
        # Cleanup
        await real_redis_client.delete_key(test_key)