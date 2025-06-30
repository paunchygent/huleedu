"""
Unit tests for Redis Pub/Sub functionality.

Tests publish and subscribe operations, proper resource cleanup, and helper methods.
Follows established testing patterns with boundary mocking and real handler functions.
"""

import asyncio
import json
from collections.abc import AsyncGenerator

import pytest
from huleedu_service_libs.redis_client import RedisClient


class MockPubSub:
    """Mock Redis PubSub object for testing subscribe functionality."""

    def __init__(self, redis_client: "MockRedisClientWithPubSub"):
        self.redis_client = redis_client
        self.subscribed_channels: set[str] = set()
        self.is_closed = False

    async def subscribe(self, channel: str) -> None:
        """Mock subscribe to a channel."""
        if self.is_closed:
            raise RuntimeError("PubSub object is closed")

        self.subscribed_channels.add(channel)
        self.redis_client.subscribe_calls.append(channel)

    async def unsubscribe(self, channel: str) -> None:
        """Mock unsubscribe from a channel."""
        if self.is_closed:
            raise RuntimeError("PubSub object is closed")

        self.subscribed_channels.discard(channel)
        self.redis_client.unsubscribe_calls.append(channel)

    async def aclose(self) -> None:
        """Mock close the PubSub connection."""
        self.is_closed = True
        self.redis_client.aclose_calls += 1

    async def listen(self) -> AsyncGenerator[dict, None]:
        """Mock message listening."""
        for message in self.redis_client.mock_messages:
            yield message


class MockRedisClientWithPubSub:
    """Mock Redis client with pub/sub functionality for testing boundaries."""

    def __init__(self):
        # Basic Redis operations
        self.keys: dict[str, str] = {}
        self.publish_calls: list[tuple[str, str]] = []
        self.subscribe_calls: list[str] = []
        self.unsubscribe_calls: list[str] = []
        self.aclose_calls = 0

        # Mock message queue for testing
        self.mock_messages: list[dict] = []

        # Error simulation
        self.should_fail_publish = False
        self.should_fail_subscribe = False
        self.should_fail_unsubscribe = False

    async def publish(self, channel: str, message: str) -> int:
        """Mock Redis PUBLISH operation."""
        self.publish_calls.append((channel, message))

        if self.should_fail_publish:
            raise Exception("Mock Redis publish error")

        # Simulate receiver count
        return 2

    def pubsub(self) -> MockPubSub:
        """Mock Redis PUBSUB operation."""
        return MockPubSub(redis_client=self)

    # Basic Redis operations (for compatibility)
    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        if key in self.keys:
            return False
        self.keys[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        self.keys[key] = value
        return True

    async def delete_key(self, key: str) -> int:
        if key in self.keys:
            del self.keys[key]
            return 1
        return 0


@pytest.fixture
def mock_redis_client_with_pubsub() -> MockRedisClientWithPubSub:
    """Provide a mock Redis client with pub/sub functionality."""
    return MockRedisClientWithPubSub()


@pytest.fixture
def redis_client_with_mock(mock_redis_client_with_pubsub: MockRedisClientWithPubSub) -> RedisClient:
    """Provide RedisClient with mocked Redis connection."""
    from huleedu_service_libs.redis_pubsub import RedisPubSub
    
    client = RedisClient(client_id="test-client", redis_url="redis://localhost:6379")
    client._started = True
    client.client = mock_redis_client_with_pubsub
    client._pubsub = RedisPubSub(mock_redis_client_with_pubsub, "test-client")
    return client


class TestRedisPubSubFunctionality:
    """Test Redis pub/sub operations with proper boundary mocking."""

    @pytest.mark.asyncio
    async def test_publish_message_success(
        self,
        redis_client_with_mock: RedisClient,
        mock_redis_client_with_pubsub: MockRedisClientWithPubSub,
    ):
        """Test successful message publishing."""
        channel = "test:channel"
        message = "test message"

        # Publish message
        result = await redis_client_with_mock.publish(channel, message)

        # Verify result and calls
        assert result == 2
        assert len(mock_redis_client_with_pubsub.publish_calls) == 1
        assert mock_redis_client_with_pubsub.publish_calls[0] == (channel, message)

    @pytest.mark.asyncio
    async def test_publish_not_started_raises_error(self):
        """Test that publish raises error when client not started."""
        client = RedisClient(client_id="test-client", redis_url="redis://localhost:6379")
        # Don't start the client

        with pytest.raises(RuntimeError, match="Redis client 'test-client' is not running"):
            await client.publish("test:channel", "message")

    @pytest.mark.asyncio
    async def test_publish_error_handling(
        self,
        redis_client_with_mock: RedisClient,
        mock_redis_client_with_pubsub: MockRedisClientWithPubSub,
    ):
        """Test publish error handling."""
        mock_redis_client_with_pubsub.should_fail_publish = True

        with pytest.raises(Exception, match="Mock Redis publish error"):
            await redis_client_with_mock.publish("test:channel", "message")

    @pytest.mark.asyncio
    async def test_subscribe_context_manager_success(
        self,
        redis_client_with_mock: RedisClient,
        mock_redis_client_with_pubsub: MockRedisClientWithPubSub,
    ):
        """Test subscription context manager with proper cleanup."""
        channel = "test:channel"

        async with redis_client_with_mock.subscribe(channel) as pubsub:
            # Verify subscribe was called
            assert len(mock_redis_client_with_pubsub.subscribe_calls) == 1
            assert mock_redis_client_with_pubsub.subscribe_calls[0] == channel

            # Verify we get the pubsub object
            assert isinstance(pubsub, MockPubSub)

        # Verify cleanup was called
        assert len(mock_redis_client_with_pubsub.unsubscribe_calls) == 1
        assert mock_redis_client_with_pubsub.unsubscribe_calls[0] == channel
        assert mock_redis_client_with_pubsub.aclose_calls == 1

    @pytest.mark.asyncio
    async def test_subscribe_not_started_raises_error(self):
        """Test that subscribe raises error when client not started."""
        client = RedisClient(client_id="test-client", redis_url="redis://localhost:6379")
        # Don't start the client

        with pytest.raises(RuntimeError, match="Redis client 'test-client' is not running"):
            async with client.subscribe("test:channel"):
                pass

    @pytest.mark.asyncio
    async def test_get_user_channel(self, redis_client_with_mock: RedisClient):
        """Test user channel helper method."""
        user_id = "test_user_123"
        channel = redis_client_with_mock.get_user_channel(user_id)
        assert channel == "ws:test_user_123"

    @pytest.mark.asyncio
    async def test_publish_user_notification(
        self,
        redis_client_with_mock: RedisClient,
        mock_redis_client_with_pubsub: MockRedisClientWithPubSub,
    ):
        """Test user notification publishing."""
        user_id = "notification_user"
        event_type = "batch_status_update"
        data = {"batch_id": "123", "status": "completed"}

        result = await redis_client_with_mock.publish_user_notification(user_id, event_type, data)

        # Verify publish was called with correct channel and message
        assert result == 2
        assert len(mock_redis_client_with_pubsub.publish_calls) == 1

        channel, message = mock_redis_client_with_pubsub.publish_calls[0]
        assert channel == "ws:notification_user"

        # Verify message structure
        parsed_message = json.loads(message)
        assert parsed_message["event"] == event_type
        assert parsed_message["data"] == data

    @pytest.mark.asyncio
    async def test_concurrent_publish_operations(
        self,
        redis_client_with_mock: RedisClient,
        mock_redis_client_with_pubsub: MockRedisClientWithPubSub,
    ):
        """Test concurrent publish operations."""
        tasks = []
        for i in range(5):
            task = redis_client_with_mock.publish(f"channel_{i}", f"message_{i}")
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Verify all publishes succeeded
        assert all(result == 2 for result in results)
        assert len(mock_redis_client_with_pubsub.publish_calls) == 5

        # Verify correct channels and messages
        for i in range(5):
            channel, message = mock_redis_client_with_pubsub.publish_calls[i]
            assert channel == f"channel_{i}"
            assert message == f"message_{i}"

    @pytest.mark.asyncio
    async def test_message_listening_simulation(
        self,
        redis_client_with_mock: RedisClient,
        mock_redis_client_with_pubsub: MockRedisClientWithPubSub,
    ):
        """Test simulated message listening pattern."""
        # Set up mock messages
        mock_redis_client_with_pubsub.mock_messages = [
            {"type": "subscribe", "channel": "test:channel", "data": 1},
            {"type": "message", "channel": "test:channel", "data": "hello"},
            {"type": "message", "channel": "test:channel", "data": "world"},
        ]

        messages = []
        async with redis_client_with_mock.subscribe("test:channel") as pubsub:
            async for message in pubsub.listen():
                messages.append(message)
                if len(messages) >= 3:  # Prevent infinite loop
                    break

        # Verify messages were received
        assert len(messages) == 3
        assert messages[0]["type"] == "subscribe"
        assert messages[1]["data"] == "hello"
        assert messages[2]["data"] == "world"

    @pytest.mark.asyncio
    async def test_helper_methods_integration(
        self,
        redis_client_with_mock: RedisClient,
        mock_redis_client_with_pubsub: MockRedisClientWithPubSub,
    ):
        """Test integration of helper methods with core pub/sub functionality."""
        user_id = "integration_test_user"

        # Use helper method to publish notification
        await redis_client_with_mock.publish_user_notification(
            user_id,
            "test_integration",
            {"data": "success"},
        )

        # Verify correct channel was used
        channel, message = mock_redis_client_with_pubsub.publish_calls[0]
        expected_channel = redis_client_with_mock.get_user_channel(user_id)
        assert channel == expected_channel == "ws:integration_test_user"

        # Verify message format
        parsed_message = json.loads(message)
        assert parsed_message["event"] == "test_integration"
        assert parsed_message["data"] == {"data": "success"}
