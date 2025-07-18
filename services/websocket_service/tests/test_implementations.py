"""
Unit tests for WebSocket Service implementations.

Tests the core implementations: WebSocketManager, JWTValidator, and MessageListener.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from fastapi import WebSocket

from services.websocket_service.implementations.jwt_validator import JWTValidator
from services.websocket_service.implementations.message_listener import RedisMessageListener
from services.websocket_service.implementations.websocket_manager import WebSocketManager


class TestWebSocketManager:
    """Test suite for WebSocket connection manager."""

    @pytest.mark.asyncio
    async def test_connect_new_user(self):
        """Test connecting a new user."""
        manager = WebSocketManager(max_connections_per_user=3)
        ws = AsyncMock(spec=WebSocket)

        await manager.connect(ws, "user123")

        assert manager.get_connection_count("user123") == 1
        assert manager.get_total_connections() == 1

    @pytest.mark.asyncio
    async def test_connect_multiple_connections_same_user(self):
        """Test multiple connections for the same user."""
        manager = WebSocketManager(max_connections_per_user=3)
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)
        ws3 = AsyncMock(spec=WebSocket)

        await manager.connect(ws1, "user123")
        await manager.connect(ws2, "user123")
        await manager.connect(ws3, "user123")

        assert manager.get_connection_count("user123") == 3
        assert manager.get_total_connections() == 3

    @pytest.mark.asyncio
    async def test_connect_exceeds_limit(self):
        """Test connection limit enforcement."""
        manager = WebSocketManager(max_connections_per_user=2)
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)
        ws3 = AsyncMock(spec=WebSocket)

        await manager.connect(ws1, "user123")
        await manager.connect(ws2, "user123")
        await manager.connect(ws3, "user123")

        # Should have closed the oldest connection
        ws1.close.assert_called_once()
        assert manager.get_connection_count("user123") == 2

    @pytest.mark.asyncio
    async def test_disconnect_existing_connection(self):
        """Test disconnecting an existing connection."""
        manager = WebSocketManager()
        ws = AsyncMock(spec=WebSocket)

        await manager.connect(ws, "user123")
        await manager.disconnect(ws, "user123")

        assert manager.get_connection_count("user123") == 0
        assert manager.get_total_connections() == 0

    @pytest.mark.asyncio
    async def test_disconnect_non_existent_connection(self):
        """Test disconnecting a non-existent connection."""
        manager = WebSocketManager()
        ws = AsyncMock(spec=WebSocket)

        # Should not raise error
        await manager.disconnect(ws, "user123")

        assert manager.get_connection_count("user123") == 0

    @pytest.mark.asyncio
    async def test_send_message_to_user_with_connections(self):
        """Test sending message to user with active connections."""
        manager = WebSocketManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)

        await manager.connect(ws1, "user123")
        await manager.connect(ws2, "user123")

        sent_count = await manager.send_message_to_user("user123", "test message")

        assert sent_count == 2
        ws1.send_text.assert_called_once_with("test message")
        ws2.send_text.assert_called_once_with("test message")

    @pytest.mark.asyncio
    async def test_send_message_to_user_no_connections(self):
        """Test sending message to user with no connections."""
        manager = WebSocketManager()

        sent_count = await manager.send_message_to_user("user123", "test message")

        assert sent_count == 0

    @pytest.mark.asyncio
    async def test_send_message_with_failed_connection(self):
        """Test sending message when some connections fail."""
        manager = WebSocketManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)
        ws2.send_text.side_effect = Exception("Connection closed")

        await manager.connect(ws1, "user123")
        await manager.connect(ws2, "user123")

        sent_count = await manager.send_message_to_user("user123", "test message")

        assert sent_count == 1
        assert manager.get_connection_count("user123") == 1

    @pytest.mark.asyncio
    async def test_multiple_users_isolation(self):
        """Test that different users' connections are isolated."""
        manager = WebSocketManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)

        await manager.connect(ws1, "user1")
        await manager.connect(ws2, "user2")

        assert manager.get_connection_count("user1") == 1
        assert manager.get_connection_count("user2") == 1
        assert manager.get_total_connections() == 2


class TestJWTValidator:
    """Test suite for JWT token validator."""

    @pytest.mark.asyncio
    async def test_validate_valid_token(self):
        """Test validation of a valid JWT token."""
        secret = "test-secret"
        validator = JWTValidator(secret_key=secret)

        # Create a valid token
        payload = {
            "sub": "user123",
            "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
        }
        token = jwt.encode(payload, secret, algorithm="HS256")

        user_id = await validator.validate_token(token)

        assert user_id == "user123"

    @pytest.mark.asyncio
    async def test_validate_expired_token(self):
        """Test validation of an expired token."""
        secret = "test-secret"
        validator = JWTValidator(secret_key=secret)

        # Create an expired token
        payload = {
            "sub": "user123",
            "exp": (datetime.now(UTC) - timedelta(hours=1)).timestamp(),
        }
        token = jwt.encode(payload, secret, algorithm="HS256")

        user_id = await validator.validate_token(token)

        assert user_id is None

    @pytest.mark.asyncio
    async def test_validate_token_missing_exp(self):
        """Test validation of token without expiration."""
        secret = "test-secret"
        validator = JWTValidator(secret_key=secret)

        # Create token without exp
        payload = {"sub": "user123"}
        token = jwt.encode(payload, secret, algorithm="HS256")

        user_id = await validator.validate_token(token)

        assert user_id is None

    @pytest.mark.asyncio
    async def test_validate_token_missing_sub(self):
        """Test validation of token without subject."""
        secret = "test-secret"
        validator = JWTValidator(secret_key=secret)

        # Create token without sub
        payload = {
            "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
        }
        token = jwt.encode(payload, secret, algorithm="HS256")

        user_id = await validator.validate_token(token)

        assert user_id is None

    @pytest.mark.asyncio
    async def test_validate_invalid_signature(self):
        """Test validation of token with invalid signature."""
        validator = JWTValidator(secret_key="correct-secret")

        # Create token with different secret
        payload = {
            "sub": "user123",
            "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
        }
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")

        user_id = await validator.validate_token(token)

        assert user_id is None

    @pytest.mark.asyncio
    async def test_validate_malformed_token(self):
        """Test validation of malformed token."""
        validator = JWTValidator(secret_key="test-secret")

        user_id = await validator.validate_token("not.a.jwt")

        assert user_id is None


class TestRedisMessageListener:
    """Test suite for Redis message listener."""

    @pytest.mark.asyncio
    async def test_start_listening_successful(self):
        """Test successful message listening setup."""
        redis_client = MagicMock()
        redis_client.get_user_channel.return_value = "ws:user123"

        # Mock pubsub subscription
        mock_pubsub = AsyncMock()
        mock_pubsub.get_message = AsyncMock(return_value=None)

        async def mock_subscribe(channel):
            yield mock_pubsub

        redis_client.subscribe = mock_subscribe

        ws_manager = AsyncMock()
        ws = AsyncMock()
        ws.receive_text = AsyncMock(side_effect=Exception("Disconnect"))

        listener = RedisMessageListener(redis_client, ws_manager)

        await listener.start_listening("user123", ws)

        # Verify setup
        redis_client.get_user_channel.assert_called_with("user123")

    @pytest.mark.asyncio
    async def test_message_forwarding(self):
        """Test forwarding messages from Redis to WebSocket."""
        redis_client = MagicMock()
        redis_client.get_user_channel.return_value = "ws:user123"

        # Mock message from Redis
        test_message = {
            "type": "message",
            "data": b'{"event": "test", "data": "hello"}',
        }

        mock_pubsub = AsyncMock()
        mock_pubsub.get_message = AsyncMock(side_effect=[test_message, None])

        async def mock_subscribe(channel):
            yield mock_pubsub

        redis_client.subscribe = mock_subscribe

        ws_manager = AsyncMock()
        ws = AsyncMock()

        # Create a task that will cancel after processing
        listener = RedisMessageListener(redis_client, ws_manager)

        # Use a task to control the listening lifecycle
        listen_task = asyncio.create_task(listener._redis_listener("user123", ws))

        # Give it time to process
        await asyncio.sleep(0.1)

        # Cancel the task
        listen_task.cancel()
        try:
            await listen_task
        except asyncio.CancelledError:
            pass

        # Verify message was forwarded
        ws_manager.send_message_to_user.assert_called_with(
            "user123", '{"event": "test", "data": "hello"}'
        )
