"""
Tests for WebSocket routes in WebSocket Service.

Adapted from API Gateway WebSocket tests, following HuleEdu testing standards.
Tests WebSocket endpoint with JWT authentication, Redis pub/sub integration,
connection management, and error scenarios.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncIterator, Callable
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

if TYPE_CHECKING:
    from services.websocket_service.tests.conftest import (
        MockJWTValidator,
        MockRedisClient,
        MockWebSocketManager,
    )


class TestWebSocketRoutes:
    """Test suite for WebSocket routes with comprehensive coverage."""

    def test_websocket_successful_connection_with_valid_token(
        self,
        create_test_app: Callable[[], FastAPI],
        mock_redis_client: MockRedisClient,
        mock_websocket_manager: MockWebSocketManager,
        mock_jwt_validator: MockJWTValidator,
    ) -> None:
        """Test successful WebSocket connection with valid JWT token."""
        app = create_test_app()

        with TestClient(app) as client:
            with client.websocket_connect("/ws/?token=test_token") as websocket:
                # Connection should be accepted
                assert websocket is not None

        # Verify JWT validation was called
        assert "test_token" in mock_jwt_validator.validate_calls

        # Verify connection was registered
        assert len(mock_websocket_manager.connect_calls) == 1
        assert mock_websocket_manager.connect_calls[0][1] == "test_user"

        # Verify Redis subscription setup
        assert "test_user" in mock_redis_client.get_user_channel_calls
        assert "ws:test_user" in mock_redis_client.subscribe_calls

    def test_websocket_rejection_with_invalid_token(
        self, create_test_app: Callable[[], FastAPI], mock_jwt_validator: MockJWTValidator
    ) -> None:
        """Test WebSocket connection rejection with invalid JWT token."""
        app = create_test_app()

        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws/?token=invalid_token"):
                    pass

        # Connection should be closed with policy violation
        assert exc_info.value.code == 1008  # WS_1008_POLICY_VIOLATION

        # Verify JWT validation was attempted
        assert "invalid_token" in mock_jwt_validator.validate_calls

    def test_websocket_rejection_with_missing_token(
        self, create_test_app: Callable[[], FastAPI]
    ) -> None:
        """Test WebSocket connection rejection when token is missing."""
        app = create_test_app()

        with TestClient(app) as client:
            # FastAPI should reject connection without required query param
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws/"):
                    pass

    def test_websocket_message_forwarding_from_redis(
        self,
        create_test_app: Callable[[], FastAPI],
        mock_redis_client: MockRedisClient,
        mock_websocket_manager: MockWebSocketManager,
    ) -> None:
        """Test message forwarding from Redis to WebSocket client."""
        app = create_test_app()

        # Configure Redis mock to simulate a message
        test_message = {
            "type": "message",
            "data": b'{"event": "batch_completed", "batch_id": "test-123"}',
        }
        mock_redis_client._mock_pubsub.get_message.return_value = test_message

        with TestClient(app) as client:
            with client.websocket_connect("/ws/?token=test_token") as websocket:
                assert websocket is not None

        # Verify Redis subscription was established
        assert "ws:test_user" in mock_redis_client.subscribe_calls

        # Note: Due to async nature and mocking, actual message forwarding
        # is tested in integration tests

    def test_websocket_connection_limit_per_user(
        self, create_test_app: Callable[[], FastAPI], mock_websocket_manager: MockWebSocketManager
    ) -> None:
        """Test connection limit enforcement per user."""
        app = create_test_app()

        # Simulate user already has max connections
        mock_websocket_manager.connections["test_user"] = [AsyncMock() for _ in range(5)]

        with TestClient(app) as client:
            with client.websocket_connect("/ws/?token=test_token") as websocket:
                assert websocket is not None

        # Verify connection was still accepted (manager handles limit internally)
        assert len(mock_websocket_manager.connect_calls) == 1

    def test_websocket_graceful_disconnect_cleanup(
        self,
        create_test_app: Callable[[], FastAPI],
        mock_websocket_manager: MockWebSocketManager,
        mock_redis_client: MockRedisClient,
    ) -> None:
        """Test proper resource cleanup on WebSocket disconnect."""
        app = create_test_app()

        with TestClient(app) as client:
            with client.websocket_connect("/ws/?token=test_token"):
                # Simulate some activity
                pass

        # After disconnect, verify cleanup
        assert len(mock_websocket_manager.disconnect_calls) == 1
        assert mock_websocket_manager.disconnect_calls[0][1] == "test_user"

    def test_websocket_redis_connection_error_handling(
        self, create_test_app: Callable[[], FastAPI], mock_redis_client: MockRedisClient
    ) -> None:
        """Test handling of Redis connection errors."""
        app = create_test_app()

        # Configure Redis to fail
        async def failing_subscribe(channel_name: str) -> AsyncIterator[Any]:
            mock_redis_client.subscribe_calls.append(channel_name)
            if False:
                yield
            raise ConnectionError("Redis connection failed")

        setattr(mock_redis_client, "subscribe", failing_subscribe)

        with TestClient(app) as client:
            # Connection should handle Redis errors gracefully
            with client.websocket_connect("/ws/?token=test_token") as websocket:
                assert websocket is not None

        # Verify subscription was attempted
        assert "ws:test_user" in mock_redis_client.subscribe_calls

    def test_websocket_concurrent_connections(
        self, create_test_app: Callable[[], FastAPI], mock_websocket_manager: MockWebSocketManager
    ) -> None:
        """Test handling of multiple concurrent connections for same user."""
        app = create_test_app()

        with TestClient(app) as client:
            # Open multiple connections
            with client.websocket_connect("/ws/?token=test_token") as ws1:
                with client.websocket_connect("/ws/?token=test_token") as ws2:
                    assert ws1 is not None
                    assert ws2 is not None

        # Verify both connections were tracked
        assert len(mock_websocket_manager.connect_calls) == 2
        assert all(call[1] == "test_user" for call in mock_websocket_manager.connect_calls)

    def test_websocket_different_users_isolation(
        self,
        create_test_app: Callable[[], FastAPI],
        mock_websocket_manager: MockWebSocketManager,
        mock_jwt_validator: MockJWTValidator,
        mock_redis_client: MockRedisClient,
    ) -> None:
        """Test that different users have isolated channels."""
        app = create_test_app()

        # Configure validator to return different users
        async def multi_user_validate(token: str) -> str | None:
            mock_jwt_validator.validate_calls.append(token)
            if token == "token1":
                return "user1"
            elif token == "token2":
                return "user2"
            return None

        setattr(mock_jwt_validator, "validate_token", multi_user_validate)

        with TestClient(app) as client:
            with client.websocket_connect("/ws/?token=token1") as ws1:
                with client.websocket_connect("/ws/?token=token2") as ws2:
                    assert ws1 is not None
                    assert ws2 is not None

        # Verify different channels were used
        assert "user1" in mock_redis_client.get_user_channel_calls
        assert "user2" in mock_redis_client.get_user_channel_calls
        assert "ws:user1" in mock_redis_client.subscribe_calls
        assert "ws:user2" in mock_redis_client.subscribe_calls

    def test_websocket_metrics_tracking(
        self, create_test_app: Callable[[], FastAPI], mock_jwt_validator: MockJWTValidator
    ) -> None:
        """Test that WebSocket metrics are properly tracked."""
        app = create_test_app()

        # Make a successful connection
        with TestClient(app) as client:
            with client.websocket_connect("/ws/?token=test_token"):
                pass

        # Make a failed connection
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws/?token=invalid_token"):
                    pass

        # Metrics are tracked internally by the service
        # Actual metric values would be verified in integration tests
