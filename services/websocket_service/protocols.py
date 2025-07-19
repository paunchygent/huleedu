from __future__ import annotations

from typing import Any, Protocol


class WebSocketManagerProtocol(Protocol):
    """
    Protocol for managing WebSocket connections.
    """

    async def connect(self, websocket: Any, user_id: str) -> bool:
        """
        Add a new WebSocket connection for a user.
        Returns True if connection was successful, False if connection limit exceeded.
        """
        ...

    async def disconnect(self, websocket: Any, user_id: str) -> None:
        """Remove a WebSocket connection for a user."""
        ...

    async def send_message_to_user(self, user_id: str, message: str) -> int:
        """
        Send a message to all connections for a user.
        Returns the number of connections that received the message.
        """
        ...

    def get_connection_count(self, user_id: str) -> int:
        """Get the number of active connections for a user."""
        ...

    def get_total_connections(self) -> int:
        """Get the total number of active connections across all users."""
        ...


class JWTValidatorProtocol(Protocol):
    """
    Protocol for JWT token validation.
    """

    async def validate_token(self, token: str) -> str:
        """
        Validate a JWT token and return the user ID if valid.
        Raises HuleEduError if the token is invalid.
        """
        ...


class MessageListenerProtocol(Protocol):
    """
    Protocol for listening to messages from Redis pub/sub.
    """

    async def start_listening(self, user_id: str, websocket: Any) -> None:
        """
        Start listening for messages for a specific user and forward them to the WebSocket.
        This should handle the entire lifecycle of the listener.
        """
        ...
