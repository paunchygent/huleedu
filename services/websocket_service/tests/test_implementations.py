"""
Unit tests for WebSocket Service implementations.

Tests the core implementations: WebSocketManager, JWTValidator, and MessageListener.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from fastapi import WebSocket
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.testing.jwt_helpers import create_jwt
from pydantic import SecretStr

from services.websocket_service.config import Settings
from services.websocket_service.implementations.jwt_validator import JWTValidator
from services.websocket_service.implementations.message_listener import RedisMessageListener
from services.websocket_service.implementations.websocket_manager import WebSocketManager


class TestWebSocketManager:
    """Test suite for WebSocket connection manager."""

    @pytest.mark.asyncio
    async def test_connect_new_user(self) -> None:
        """Test connecting a new user."""
        manager = WebSocketManager(max_connections_per_user=3)
        ws = AsyncMock(spec=WebSocket)

        await manager.connect(ws, "user123")

        assert manager.get_connection_count("user123") == 1
        assert manager.get_total_connections() == 1

    @pytest.mark.asyncio
    async def test_connect_multiple_connections_same_user(self) -> None:
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
    async def test_connect_exceeds_limit(self) -> None:
        """Test connection limit enforcement."""
        manager = WebSocketManager(max_connections_per_user=2)
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)
        ws3 = AsyncMock(spec=WebSocket)

        # First two connections should succeed
        result1 = await manager.connect(ws1, "user123")
        result2 = await manager.connect(ws2, "user123")
        assert result1 is True
        assert result2 is True

        # Third connection should be rejected
        result3 = await manager.connect(ws3, "user123")
        assert result3 is False

        # No connections should be closed automatically
        ws1.close.assert_not_called()
        ws2.close.assert_not_called()
        ws3.close.assert_not_called()

        # Should still have only 2 connections (third was rejected)
        assert manager.get_connection_count("user123") == 2
        assert manager.get_total_connections() == 2

    @pytest.mark.asyncio
    async def test_disconnect_existing_connection(self) -> None:
        """Test disconnecting an existing connection."""
        manager = WebSocketManager()
        ws = AsyncMock(spec=WebSocket)

        await manager.connect(ws, "user123")
        await manager.disconnect(ws, "user123")

        assert manager.get_connection_count("user123") == 0
        assert manager.get_total_connections() == 0

    @pytest.mark.asyncio
    async def test_disconnect_non_existent_connection(self) -> None:
        """Test disconnecting a non-existent connection."""
        manager = WebSocketManager()
        ws = AsyncMock(spec=WebSocket)

        # Should not raise error
        await manager.disconnect(ws, "user123")

        assert manager.get_connection_count("user123") == 0

    @pytest.mark.asyncio
    async def test_send_message_to_user_with_connections(self) -> None:
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
    async def test_send_message_to_user_no_connections(self) -> None:
        """Test sending message to user with no connections."""
        manager = WebSocketManager()

        sent_count = await manager.send_message_to_user("user123", "test message")

        assert sent_count == 0

    @pytest.mark.asyncio
    async def test_send_message_with_failed_connection(self) -> None:
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
    async def test_multiple_users_isolation(self) -> None:
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

    @pytest.fixture
    def settings(self) -> Settings:
        """Provide test settings for JWT validation."""
        return Settings(
            SERVICE_NAME="websocket_service",
            JWT_SECRET_KEY=SecretStr("test-secret"),
        )

    @pytest.mark.asyncio
    async def test_validate_valid_token(self, settings: Settings) -> None:
        """Test validation of a valid JWT token."""
        validator = JWTValidator(secret_key=settings.JWT_SECRET_KEY.get_secret_value())

        # Create a valid token
        payload = {
            "sub": "user123",
            "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
            "aud": settings.JWT_AUDIENCE,
            "iss": settings.JWT_ISSUER,
        }
        token = create_jwt(
            secret=settings.JWT_SECRET_KEY.get_secret_value(),
            payload=payload,
            algorithm=settings.JWT_ALGORITHM,
        )

        user_id = await validator.validate_token(token)

        assert user_id == "user123"

    @pytest.mark.asyncio
    async def test_validate_expired_token(self, settings: Settings) -> None:
        """Test validation of an expired token."""
        validator = JWTValidator(secret_key=settings.JWT_SECRET_KEY.get_secret_value())

        # Create an expired token
        payload = {
            "sub": "user123",
            "exp": (datetime.now(UTC) - timedelta(hours=1)).timestamp(),
            "aud": settings.JWT_AUDIENCE,
            "iss": settings.JWT_ISSUER,
        }
        token = create_jwt(
            secret=settings.JWT_SECRET_KEY.get_secret_value(),
            payload=payload,
            algorithm=settings.JWT_ALGORITHM,
        )

        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_token(token)

        assert "token has expired" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_validate_token_missing_exp(self, settings: Settings) -> None:
        """Test validation of token without expiration."""
        validator = JWTValidator(secret_key=settings.JWT_SECRET_KEY.get_secret_value())

        # Create token without exp
        payload = {"sub": "user123", "aud": settings.JWT_AUDIENCE, "iss": settings.JWT_ISSUER}
        token = create_jwt(
            secret=settings.JWT_SECRET_KEY.get_secret_value(),
            payload=payload,
            algorithm=settings.JWT_ALGORITHM,
        )

        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_token(token)

        assert "missing expiration" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_validate_token_missing_sub(self, settings: Settings) -> None:
        """Test validation of token without subject."""
        validator = JWTValidator(secret_key=settings.JWT_SECRET_KEY.get_secret_value())

        # Create token without sub
        payload = {
            "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
            "aud": settings.JWT_AUDIENCE,
            "iss": settings.JWT_ISSUER,
        }
        token = create_jwt(
            secret=settings.JWT_SECRET_KEY.get_secret_value(),
            payload=payload,
            algorithm=settings.JWT_ALGORITHM,
        )

        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_token(token)

        assert "missing subject" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_validate_invalid_signature(self, settings: Settings) -> None:
        """Test validation of token with invalid signature."""
        validator = JWTValidator(secret_key=settings.JWT_SECRET_KEY.get_secret_value())

        # Create token with different secret
        payload = {
            "sub": "user123",
            "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
            "aud": settings.JWT_AUDIENCE,
            "iss": settings.JWT_ISSUER,
        }
        token = create_jwt(secret="wrong-secret", payload=payload, algorithm=settings.JWT_ALGORITHM)

        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_token(token)

        assert "signature verification failed" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_validate_malformed_token(self) -> None:
        """Test validation of malformed token."""
        validator = JWTValidator(secret_key="test-secret")

        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_token("not.a.jwt")

        assert "invalid token" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_invalid_audience_rejection(self, settings: Settings) -> None:
        """Token with wrong audience should be rejected by audience validation."""
        validator = JWTValidator(secret_key=settings.JWT_SECRET_KEY.get_secret_value())

        payload = {
            "sub": "user123",
            "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
            "aud": "wrong-audience",
            "iss": settings.JWT_ISSUER,
        }
        token = create_jwt(
            secret=settings.JWT_SECRET_KEY.get_secret_value(),
            payload=payload,
            algorithm=settings.JWT_ALGORITHM,
        )

        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_token(token)

        assert "aud" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_invalid_issuer_rejection(self, settings: Settings) -> None:
        """Token with wrong issuer should be rejected by issuer validation."""
        validator = JWTValidator(secret_key=settings.JWT_SECRET_KEY.get_secret_value())

        payload = {
            "sub": "user123",
            "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
            "aud": settings.JWT_AUDIENCE,
            "iss": "wrong-issuer",
        }
        token = create_jwt(
            secret=settings.JWT_SECRET_KEY.get_secret_value(),
            payload=payload,
            algorithm=settings.JWT_ALGORITHM,
        )

        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_token(token)

        assert "iss" in exc_info.value.error_detail.message.lower()


class TestRedisMessageListener:
    """Test suite for Redis message listener."""

    @pytest.mark.asyncio
    async def test_start_listening_successful(self) -> None:
        """Test successful message listening setup."""
        redis_client = MagicMock()
        redis_client.get_user_channel.return_value = "ws:user123"

        # Mock pubsub subscription
        mock_pubsub = AsyncMock()
        mock_pubsub.get_message = AsyncMock(return_value=None)

        @asynccontextmanager
        async def mock_subscribe(channel: str) -> AsyncIterator[Any]:
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
    async def test_message_forwarding(self) -> None:
        """Test forwarding messages from Redis to WebSocket."""
        redis_client = MagicMock()
        redis_client.get_user_channel.return_value = "ws:user123"

        # Mock message from Redis
        test_message = {
            "type": "message",
            "data": b'{"event": "test", "data": "hello"}',
        }

        mock_pubsub = AsyncMock()
        # Return test message once, then None forever to avoid StopAsyncIteration
        message_calls = [test_message] + [None] * 100  # None forever after first message
        mock_pubsub.get_message = AsyncMock(side_effect=message_calls)

        @asynccontextmanager
        async def mock_subscribe(channel: str) -> AsyncIterator[Any]:
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
