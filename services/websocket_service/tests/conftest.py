"""
Test configuration for WebSocket Service.

Implements protocol-based mocking following HuleEdu testing standards.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator, Callable
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from fastapi import FastAPI
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from prometheus_client import CollectorRegistry

from services.websocket_service.config import Settings
from services.websocket_service.metrics import WebSocketMetrics
from services.websocket_service.protocols import (
    JWTValidatorProtocol,
    MessageListenerProtocol,
    WebSocketManagerProtocol,
)


class MockRedisClient:
    """Mock Redis client for testing WebSocket functionality."""

    def __init__(self) -> None:
        self.client = AsyncMock()
        self.client.ping = AsyncMock(return_value=True)
        self.ping = AsyncMock(return_value=True)
        self.get_user_channel_calls: list[str] = []
        self.subscribe_calls: list[str] = []
        self.publish_calls: list[tuple[str, str, dict[str, Any]]] = []
        self._mock_pubsub = AsyncMock()
        self._mock_pubsub.get_message = AsyncMock(return_value=None)

        # Add required AtomicRedisClientProtocol methods
        self.set_if_not_exists = AsyncMock(return_value=True)
        self.delete_key = AsyncMock(return_value=1)
        self.get = AsyncMock(return_value=None)
        self.setex = AsyncMock(return_value=True)
        self.watch = AsyncMock(return_value=True)
        self.multi = AsyncMock(return_value=True)
        self.exec = AsyncMock(return_value=[])
        self.unwatch = AsyncMock(return_value=True)
        self.scan_pattern = AsyncMock(return_value=[])
        self.publish = AsyncMock(return_value=1)

    def get_user_channel(self, user_id: str) -> str:
        """Track channel name generation."""
        self.get_user_channel_calls.append(user_id)
        return f"ws:{user_id}"

    async def subscribe(self, channel: str) -> AsyncGenerator[Any, None]:
        """Mock subscription to Redis channel."""
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

    async def connect(self, websocket: Any, user_id: str) -> None:
        """Track connection calls."""
        self.connect_calls.append((websocket, user_id))
        if user_id not in self.connections:
            self.connections[user_id] = []
        self.connections[user_id].append(websocket)

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

    async def validate_token(self, token: str) -> str | None:
        """Mock token validation."""
        self.validate_calls.append(token)

        # Simple mock validation logic
        if token == "invalid_token":
            return None
        if token == "expired_token":
            return None
        if token.startswith("valid_"):
            # Extract user from token (e.g., "valid_user123" -> "user123")
            user_id = token.replace("valid_", "")
            if user_id in self.valid_users:
                return user_id

        # Default behavior for tests
        if token == "test_token":
            return "test_user"

        return None


class MockMessageListener:
    """Mock message listener for testing."""

    def __init__(
        self, redis_client: AtomicRedisClientProtocol, websocket_manager: WebSocketManagerProtocol
    ) -> None:
        self.redis_client = redis_client
        self.websocket_manager = websocket_manager
        self.start_listening_calls: list[tuple[str, Any]] = []

    async def start_listening(self, user_id: str, websocket: Any) -> None:
        """Mock listening to Redis messages."""
        self.start_listening_calls.append((user_id, websocket))
        # Simulate the behavior of the real listener
        channel = self.redis_client.get_user_channel(user_id)
        async for _ in self.redis_client.subscribe(channel):
            # In tests, we immediately break to avoid infinite loop
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
            JWT_SECRET_KEY="test-secret",
            REDIS_URL="redis://localhost:6379",
            WEBSOCKET_MAX_CONNECTIONS_PER_USER=5,
        )

    @provide
    async def get_redis_client(self) -> AsyncIterator[AtomicRedisClientProtocol]:
        """Provide mock Redis client."""
        # MockRedisClient implements the protocol methods for testing
        yield cast(AtomicRedisClientProtocol, self._redis_client)

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
