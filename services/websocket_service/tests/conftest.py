"""
Test configuration for WebSocket Service.

Implements protocol-based mocking following HuleEdu testing standards.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator, Callable
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import redis.client
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from fastapi import FastAPI
from huleedu_service_libs.error_handling import raise_authentication_error
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from prometheus_client import CollectorRegistry

from services.websocket_service.config import Settings
from services.websocket_service.metrics import WebSocketMetrics
from services.websocket_service.protocols import (
    JWTValidatorProtocol,
    MessageListenerProtocol,
    WebSocketManagerProtocol,
)


class MockPubSubContextManager:
    """Mock async context manager for Redis PubSub subscription."""

    def __init__(self, mock_pubsub: AsyncMock) -> None:
        self._mock_pubsub = mock_pubsub

    async def __aenter__(self) -> Any:
        return self._mock_pubsub

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class MockRedisClient(AtomicRedisClientProtocol):
    """Mock Redis client for testing WebSocket functionality."""

    # Override ping attribute type for testing
    ping: AsyncMock

    def __init__(self) -> None:
        self.client = AsyncMock()
        # Store ping as AsyncMock for test manipulation (side_effect, etc.)
        self.ping = AsyncMock(return_value=True)
        self.get_user_channel_calls: list[str] = []
        self.subscribe_calls: list[str] = []
        self.publish_calls: list[tuple[str, str, dict[str, Any]]] = []
        self._mock_pubsub = AsyncMock()
        self._mock_pubsub.get_message = AsyncMock(return_value=None)

    async def set_if_not_exists(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        """Mock set_if_not_exists method."""
        return True

    async def delete_key(self, key: str) -> int:
        """Mock delete_key method."""
        return 1

    async def get(self, key: str) -> str | None:
        """Mock get method."""
        return None

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Mock setex method."""
        return True

    async def watch(self, *keys: str) -> bool:
        """Mock watch method for transactions."""
        return True

    async def multi(self) -> bool:
        """Mock multi method for transactions."""
        return True

    async def exec(self) -> list[Any] | None:
        """Mock exec method for transactions."""
        return []

    async def unwatch(self) -> bool:
        """Mock unwatch method for transactions."""
        return True

    async def create_transaction_pipeline(self, *watch_keys: str) -> Any:
        """Mock create_transaction_pipeline method for atomic transactions."""
        # Return a mock pipeline object
        mock_pipeline = AsyncMock()
        return mock_pipeline

    async def scan_pattern(self, pattern: str) -> list[str]:
        """Mock scan_pattern method."""
        return []

    async def publish(self, channel: str, message: str) -> int:
        """Mock publish method."""
        return 1

    async def sadd(self, key: str, *members: str) -> int:
        """Mock sadd method for set operations."""
        return 1

    async def spop(self, key: str) -> str | None:
        """Mock spop method for set operations."""
        return None

    async def scard(self, key: str) -> int:
        """Mock scard method for set operations."""
        return 0

    async def smembers(self, key: str) -> set[str]:
        """Mock smembers method for set operations."""
        return set()

    async def hset(self, key: str, field: str, value: str) -> int:
        """Mock hset method for hash operations."""
        return 1

    async def hget(self, key: str, field: str) -> str | None:
        """Mock hget method for hash operations."""
        return None

    async def hlen(self, key: str) -> int:
        """Mock hlen method for hash operations."""
        return 0

    async def hgetall(self, key: str) -> dict[str, str]:
        """Mock hgetall method for hash operations."""
        return {}

    async def hexists(self, key: str, field: str) -> bool:
        """Mock hexists method for hash operations."""
        return False

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        """Mock expire method for key operations."""
        return True

    async def ttl(self, key: str) -> int:
        """Mock ttl method for key operations."""
        return -1

    async def exists(self, key: str) -> int:
        """Mock exists method for key operations."""
        return 0

    async def rpush(self, key: str, *values: str) -> int:
        """Mock rpush method for list operations."""
        return 1

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        """Mock lrange method for list operations."""
        return []

    async def llen(self, key: str) -> int:
        """Mock llen method for list operations."""
        return 0

    def get_user_channel(self, user_id: str) -> str:
        """Track channel name generation."""
        self.get_user_channel_calls.append(user_id)
        return f"ws:{user_id}"

    async def subscribe(self, channel: str) -> AsyncGenerator[redis.client.PubSub, None]:
        """Mock subscription to Redis channel with proper async generator."""
        self.subscribe_calls.append(channel)
        yield self._mock_pubsub

    async def publish_user_notification(
        self, user_id: str, event_type: str, data: dict[str, Any]
    ) -> int:
        """Mock publishing notifications."""
        self.publish_calls.append((user_id, event_type, data))
        return 1


class MockWebSocketManager:
    """Mock WebSocket manager for testing."""

    def __init__(self) -> None:
        self.connections: dict[str, list[Any]] = {}
        self.connect_calls: list[tuple[Any, str]] = []
        self.disconnect_calls: list[tuple[Any, str]] = []
        self.send_message_calls: list[tuple[str, str]] = []

    async def connect(self, websocket: Any, user_id: str) -> bool:
        """Track connection calls and return success status."""
        self.connect_calls.append((websocket, user_id))
        if user_id not in self.connections:
            self.connections[user_id] = []
        self.connections[user_id].append(websocket)

        # Return False if user already has max connections (for testing connection limits)
        max_connections = 5  # Match the test setting
        return len(self.connections[user_id]) <= max_connections

    async def disconnect(self, websocket: Any, user_id: str) -> None:
        """Track disconnection calls."""
        self.disconnect_calls.append((websocket, user_id))
        if user_id in self.connections:
            try:
                self.connections[user_id].remove(websocket)
                if not self.connections[user_id]:
                    del self.connections[user_id]
            except ValueError:
                pass

    async def send_message_to_user(self, user_id: str, message: str) -> int:
        """Track message sends."""
        self.send_message_calls.append((user_id, message))
        return len(self.connections.get(user_id, []))

    def get_connection_count(self, user_id: str) -> int:
        """Get connection count for user."""
        return len(self.connections.get(user_id, []))

    def get_total_connections(self) -> int:
        """Get total connections across all users."""
        return sum(len(conns) for conns in self.connections.values())


class MockJWTValidator:
    """Mock JWT validator for testing."""

    def __init__(self, valid_users: list[str] | None = None) -> None:
        self.valid_users = valid_users or ["test_user", "user123"]
        self.validate_calls: list[str] = []

    async def validate_token(self, token: str) -> str:
        """Mock token validation with HuleEduError for invalid tokens."""
        self.validate_calls.append(token)
        correlation_id = uuid4()

        # Simple mock validation logic
        if token == "invalid_token":
            raise_authentication_error(
                service="websocket_service",
                operation="validate_token",
                message="Invalid token provided",
                correlation_id=correlation_id,
                reason="invalid_token",
            )
        if token == "expired_token":
            raise_authentication_error(
                service="websocket_service",
                operation="validate_token",
                message="Token has expired",
                correlation_id=correlation_id,
                reason="token_expired",
            )
        if token.startswith("valid_"):
            # Extract user from token (e.g., "valid_user123" -> "user123")
            user_id = token.replace("valid_", "")
            if user_id in self.valid_users:
                return user_id
            else:
                raise_authentication_error(
                    service="websocket_service",
                    operation="validate_token",
                    message="User not found in valid users",
                    correlation_id=correlation_id,
                    reason="user_not_found",
                )

        # Default behavior for tests
        if token == "test_token":
            return "test_user"

        # Any other token is invalid
        raise_authentication_error(
            service="websocket_service",
            operation="validate_token",
            message="Unrecognized token format",
            correlation_id=correlation_id,
            reason="unrecognized_token",
        )


class MockMessageListener:
    """Mock message listener for testing."""

    def __init__(
        self, redis_client: AtomicRedisClientProtocol, websocket_manager: WebSocketManagerProtocol
    ) -> None:
        self.redis_client = redis_client
        self.websocket_manager = websocket_manager
        self.start_listening_calls: list[tuple[str, Any]] = []

    async def start_listening(self, user_id: str, websocket: Any) -> None:
        """Mock listening to Redis messages with proper Redis method calls."""
        self.start_listening_calls.append((user_id, websocket))

        # Simulate the behavior of the real listener - must call Redis methods
        channel = self.redis_client.get_user_channel(user_id)  # This will track the call

        # Use the async generator properly
        async for pubsub in self.redis_client.subscribe(channel):  # This will track the call
            # In tests, we process one message iteration to track calls
            message = await pubsub.get_message(timeout=0.001)  # Quick timeout for tests
            if message and message.get("type") == "message":
                # Would normally forward message to WebSocket
                await self.websocket_manager.send_message_to_user(
                    user_id, message["data"].decode("utf-8")
                )
            # Exit immediately to avoid infinite loop in tests
            break


class MockWebSocketServiceProvider(Provider):
    """Mock provider for WebSocket service tests."""

    scope = Scope.APP

    def __init__(
        self,
        redis_client: MockRedisClient | None = None,
        websocket_manager: MockWebSocketManager | None = None,
        jwt_validator: MockJWTValidator | None = None,
    ) -> None:
        super().__init__()
        self._redis_client = redis_client or MockRedisClient()
        self._websocket_manager = websocket_manager or MockWebSocketManager()
        self._jwt_validator = jwt_validator or MockJWTValidator()

    @provide
    def get_config(self) -> Settings:
        """Provide test settings."""
        return Settings(
            SERVICE_NAME="websocket_service",
            JWT_SECRET_KEY="test-secret",
            REDIS_URL="redis://localhost:6379",
            WEBSOCKET_MAX_CONNECTIONS_PER_USER=5,
        )

    @provide
    async def get_redis_client(self) -> AsyncIterator[AtomicRedisClientProtocol]:
        """Provide mock Redis client."""
        # MockRedisClient provides the necessary interface for testing
        # The typing conflict with subscribe method is handled by MyPy's structural typing
        yield self._redis_client  # MyPy will accept this due to structural typing compatibility

    @provide(scope=Scope.APP)
    def provide_websocket_manager(self) -> WebSocketManagerProtocol:
        """Provide mock WebSocket manager."""
        return self._websocket_manager

    @provide(scope=Scope.APP)
    def provide_jwt_validator(self) -> JWTValidatorProtocol:
        """Provide mock JWT validator."""
        return self._jwt_validator

    @provide(scope=Scope.SESSION)
    def provide_message_listener(
        self,
        redis_client: AtomicRedisClientProtocol,
        websocket_manager: WebSocketManagerProtocol,
    ) -> MessageListenerProtocol:
        """Provide mock message listener."""
        return MockMessageListener(redis_client, websocket_manager)

    @provide(scope=Scope.APP)
    def provide_registry(self) -> CollectorRegistry:
        """Provide isolated registry for tests."""
        return CollectorRegistry()

    @provide(scope=Scope.APP)
    def provide_metrics(self, registry: CollectorRegistry) -> WebSocketMetrics:
        """Provide metrics with isolated registry."""
        return WebSocketMetrics(registry=registry)


@pytest.fixture
def mock_redis_client() -> MockRedisClient:
    """Fixture for mock Redis client."""
    return MockRedisClient()


@pytest.fixture
def mock_websocket_manager() -> MockWebSocketManager:
    """Fixture for mock WebSocket manager."""
    return MockWebSocketManager()


@pytest.fixture
def mock_jwt_validator() -> MockJWTValidator:
    """Fixture for mock JWT validator."""
    return MockJWTValidator()


@pytest.fixture
async def test_container(
    mock_redis_client: MockRedisClient,
    mock_websocket_manager: MockWebSocketManager,
    mock_jwt_validator: MockJWTValidator,
) -> AsyncIterator[AsyncContainer]:
    """Create test DI container with mocks."""
    provider = MockWebSocketServiceProvider(
        redis_client=mock_redis_client,
        websocket_manager=mock_websocket_manager,
        jwt_validator=mock_jwt_validator,
    )
    container = make_async_container(provider)
    yield container
    await container.close()


@pytest.fixture
def create_test_app(test_container: AsyncContainer) -> Callable[[], FastAPI]:
    """Create test FastAPI app with mocked dependencies."""
    from dishka.integrations.fastapi import setup_dishka
    from fastapi import FastAPI

    def _create_app() -> FastAPI:
        app = FastAPI()
        setup_dishka(test_container, app)

        # Register routers
        from services.websocket_service.routers import health_routes, websocket_routes

        app.include_router(health_routes.router, tags=["Health"])
        app.include_router(websocket_routes.router, prefix="/ws", tags=["WebSocket"])

        return app

    return _create_app
