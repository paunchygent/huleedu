"""
Tests for WebSocket routes in API Gateway Service.

Tests the WebSocket /ws/v1/status/{client_id} endpoint with proper authentication,
Redis pub/sub integration, concurrency handling, and error scenarios.

Following Rule 070.1 (Protocol-based mocking) and Rule 042.2.1 (Protocol-based dependencies).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect
from prometheus_client import CollectorRegistry

from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from services.api_gateway_service.app.main import create_app
from services.api_gateway_service.app.metrics import GatewayMetrics
from services.api_gateway_service.auth import get_current_user_id


class MockWebSocketProvider(Provider):
    """Test provider with mock dependencies for WebSocket tests."""

    scope = Scope.APP

    def __init__(self):
        super().__init__()
        self.mock_redis_client = AsyncMock(spec=AtomicRedisClientProtocol)
        self.mock_redis_client.get_user_channel.return_value = "ws:test_user"

    @provide
    def get_redis_client(self) -> AtomicRedisClientProtocol:
        return self.mock_redis_client

    @provide
    def provide_metrics(self) -> GatewayMetrics:
        return GatewayMetrics(registry=CollectorRegistry())

    @provide
    def provide_registry(self) -> CollectorRegistry:
        return CollectorRegistry()


@pytest.fixture
def mock_provider():
    """Create mock provider for testing."""
    return MockWebSocketProvider()


@pytest.fixture
def mock_redis_client(mock_provider):
    """Get mock Redis client from provider."""
    return mock_provider.mock_redis_client


@pytest.fixture
async def container(mock_provider):
    """Create test container with mock dependencies."""
    container = make_async_container(mock_provider)
    yield container
    await container.close()


@pytest.fixture
def mock_auth():
    """Mock authentication to return test user."""

    def get_test_user():
        return "test_user"

    return get_test_user


@pytest.fixture
def client_with_websocket(container, mock_auth, mock_redis_client):
    """Test client with WebSocket support and mocked dependencies."""
    app = create_app()

    # Override authentication
    app.dependency_overrides[get_current_user_id] = mock_auth

    # Set up Dishka with test container
    from dishka.integrations.fastapi import setup_dishka

    setup_dishka(container, app)

    with TestClient(app) as client:
        yield client, mock_redis_client

    # Clean up overrides
    app.dependency_overrides.clear()


class TestWebSocketRoutes:
    """Test suite for WebSocket routes with comprehensive coverage."""

    def test_websocket_successful_connection_and_authentication(self, client_with_websocket):
        """Test successful WebSocket connection with valid authentication."""
        client, mock_redis_client = client_with_websocket

        # Mock Redis pub/sub behavior
        mock_pubsub = AsyncMock()
        mock_pubsub.get_message.return_value = None  # No messages initially
        mock_redis_client.subscribe.return_value = AsyncMock()
        mock_redis_client.subscribe.return_value.__aiter__.return_value = [mock_pubsub]

        with client.websocket_connect("/ws/v1/status/test_user") as websocket:
            # Connection should be accepted
            assert websocket is not None

            # Verify Redis channel subscription
            mock_redis_client.get_user_channel.assert_called_once_with("test_user")
            mock_redis_client.subscribe.assert_called_once_with("ws:test_user")

    def test_websocket_unauthorized_client_id_mismatch(self, client_with_websocket):
        """Test WebSocket connection rejection when client_id doesn't match authenticated user."""
        client, mock_redis_client = client_with_websocket

        # Try to connect with different client_id than authenticated user
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/v1/status/different_user"):
                pass

        # Connection should be closed with policy violation
        assert exc_info.value.code == 1008  # WS_1008_POLICY_VIOLATION

        # Redis should not be called for unauthorized connection
        mock_redis_client.get_user_channel.assert_not_called()
        mock_redis_client.subscribe.assert_not_called()

    def test_websocket_message_forwarding_from_redis(self, client_with_websocket):
        """Test message forwarding from Redis channel to WebSocket client."""
        client, mock_redis_client = client_with_websocket

        # Mock Redis pub/sub with a message
        mock_pubsub = AsyncMock()
        mock_message = {
            "type": "message",
            "data": b'{"status": "batch_completed", "batch_id": "test-batch-123"}',
        }
        mock_pubsub.get_message.side_effect = [mock_message, None]  # Message then timeout

        async def mock_subscribe(_channel):
            yield mock_pubsub

        mock_redis_client.subscribe.side_effect = mock_subscribe

        with client.websocket_connect("/ws/v1/status/test_user") as websocket:
            # Should receive the forwarded message
            data = websocket.receive_text()
            assert data == '{"status": "batch_completed", "batch_id": "test-batch-123"}'

    def test_websocket_redis_connection_error_handling(self, client_with_websocket):
        """Test graceful handling of Redis connection errors."""
        client, mock_redis_client = client_with_websocket

        # Mock Redis subscription failure
        mock_redis_client.subscribe.side_effect = ConnectionError("Redis connection failed")

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/v1/status/test_user"):
                pass

        # Should close with internal error
        assert exc_info.value.code == 1011  # WS_1011_INTERNAL_ERROR

    def test_websocket_graceful_disconnect_cleanup(self, client_with_websocket):
        """Test proper resource cleanup on WebSocket disconnect."""
        client, mock_redis_client = client_with_websocket

        # Mock Redis pub/sub behavior
        mock_pubsub = AsyncMock()
        mock_pubsub.get_message.return_value = None
        mock_redis_client.subscribe.return_value = AsyncMock()
        mock_redis_client.subscribe.return_value.__aiter__.return_value = [mock_pubsub]

        with client.websocket_connect("/ws/v1/status/test_user") as _websocket:
            # Connection established
            pass

        # After disconnect, Redis subscription should have been called
        mock_redis_client.subscribe.assert_called_once_with("ws:test_user")

    def test_websocket_concurrent_task_cancellation(self, client_with_websocket):
        """Test proper cancellation of Redis listener task on disconnect."""
        client, mock_redis_client = client_with_websocket

        # Mock Redis pub/sub that simulates long-running subscription
        mock_pubsub = AsyncMock()
        mock_pubsub.get_message.side_effect = asyncio.CancelledError()

        async def mock_subscribe(_channel):
            yield mock_pubsub

        mock_redis_client.subscribe.side_effect = mock_subscribe

        with client.websocket_connect("/ws/v1/status/test_user") as _websocket:
            # Connection should handle cancellation gracefully
            pass

        # Redis subscription should have been called before cancellation
        mock_redis_client.subscribe.assert_called_once_with("ws:test_user")

    def test_websocket_message_filtering_non_message_types(self, client_with_websocket):
        """Test filtering of non-message type Redis events."""
        client, mock_redis_client = client_with_websocket

        # Mock Redis pub/sub with subscribe confirmation (should be ignored)
        mock_pubsub = AsyncMock()
        mock_subscribe_confirmation = {"type": "subscribe", "data": b"1"}
        mock_actual_message = {"type": "message", "data": b'{"status": "processing"}'}
        mock_pubsub.get_message.side_effect = [
            mock_subscribe_confirmation,
            mock_actual_message,
            None,
        ]

        async def mock_subscribe(_channel):
            yield mock_pubsub

        mock_redis_client.subscribe.side_effect = mock_subscribe

        with client.websocket_connect("/ws/v1/status/test_user") as websocket:
            # Should only receive the actual message, not subscribe confirmation
            data = websocket.receive_text()
            assert data == '{"status": "processing"}'

    def test_websocket_authentication_integration(self, container, mock_redis_client):
        """Test WebSocket authentication integration with JWT validation."""
        app = create_app()

        # Mock authentication failure
        def mock_auth_failure():
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        app.dependency_overrides[get_current_user_id] = mock_auth_failure

        # Set up Dishka with test container
        from dishka.integrations.fastapi import setup_dishka

        setup_dishka(container, app)

        with TestClient(app) as client:
            # WebSocket connection should fail due to authentication
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws/v1/status/test_user"):
                    pass

        # Redis should not be called for failed authentication
        mock_redis_client.get_user_channel.assert_not_called()
        mock_redis_client.subscribe.assert_not_called()

    def test_websocket_user_channel_naming_convention(self, client_with_websocket):
        """Test that WebSocket uses correct user channel naming convention."""
        client, mock_redis_client = client_with_websocket

        # Mock Redis pub/sub behavior
        mock_pubsub = AsyncMock()
        mock_pubsub.get_message.return_value = None
        mock_redis_client.subscribe.return_value = AsyncMock()
        mock_redis_client.subscribe.return_value.__aiter__.return_value = [mock_pubsub]

        with client.websocket_connect("/ws/v1/status/test_user") as _websocket:
            # Verify correct channel naming convention
            mock_redis_client.get_user_channel.assert_called_once_with("test_user")

            # Verify subscription to the returned channel name
            mock_redis_client.subscribe.assert_called_once_with("ws:test_user")

    def test_websocket_redis_timeout_handling(self, client_with_websocket):
        """Test WebSocket handling of Redis message timeouts."""
        client, mock_redis_client = client_with_websocket

        # Mock Redis pub/sub with timeouts (None return values)
        mock_pubsub = AsyncMock()
        mock_pubsub.get_message.return_value = None  # Simulates timeout

        async def mock_subscribe(_channel):
            yield mock_pubsub

        mock_redis_client.subscribe.side_effect = mock_subscribe

        with client.websocket_connect("/ws/v1/status/test_user") as _websocket:
            # Connection should remain stable despite Redis timeouts
            pass

        # Redis subscription should be called normally
        mock_redis_client.subscribe.assert_called_once_with("ws:test_user")

        # get_message should be called with timeout parameter
        mock_pubsub.get_message.assert_called_with(ignore_subscribe_messages=True, timeout=1.0)
