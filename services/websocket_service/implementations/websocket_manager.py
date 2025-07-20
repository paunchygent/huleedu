from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("websocket.manager")


class WebSocketManager:
    """
    Manages WebSocket connections for users.
    Implements connection tracking and message broadcasting.
    """

    def __init__(self, max_connections_per_user: int = 5) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._max_connections_per_user = max_connections_per_user
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str) -> bool:
        """
        Add a new WebSocket connection for a user.
        Returns True if connection was successful, False if connection limit exceeded.
        """
        async with self._lock:
            user_connections = self._connections[user_id]

            # Check connection limit
            if len(user_connections) >= self._max_connections_per_user:
                logger.warning(
                    f"User {user_id} exceeded max connections ({self._max_connections_per_user})",
                    extra={
                        "user_id": user_id,
                        "current_connections": len(user_connections),
                    },
                )
                # Reject the new connection instead of removing old ones
                return False

            self._connections[user_id].append(websocket)
            total_conns = len(self._connections[user_id])
            logger.info(
                f"WebSocket connected for user {user_id}. Total connections: {total_conns}",
                extra={"user_id": user_id, "total_connections": total_conns},
            )
            return True

    async def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        """Remove a WebSocket connection for a user."""
        async with self._lock:
            if user_id in self._connections:
                try:
                    self._connections[user_id].remove(websocket)
                    if not self._connections[user_id]:
                        # Clean up empty lists
                        del self._connections[user_id]
                    remaining = len(self._connections.get(user_id, []))
                    logger.info(
                        "WebSocket disconnected for user %s. Remaining connections: %s",
                        user_id,
                        remaining,
                        extra={
                            "user_id": user_id,
                            "remaining_connections": remaining,
                        },
                    )
                except ValueError:
                    logger.warning(
                        f"Attempted to remove non-existent WebSocket for user {user_id}",
                        extra={"user_id": user_id},
                    )

    async def send_message_to_user(self, user_id: str, message: str) -> int:
        """
        Send a message to all connections for a user.
        Returns the number of connections that received the message.
        """
        async with self._lock:
            connections = self._connections.get(user_id, [])
            if not connections:
                logger.debug(
                    f"No active connections for user {user_id}",
                    extra={"user_id": user_id},
                )
                return 0

            sent_count = 0
            disconnected: list[WebSocket] = []

            for websocket in connections:
                try:
                    await websocket.send_text(message)
                    sent_count += 1
                except Exception as e:
                    logger.error(
                        f"Failed to send message to user {user_id}: {e}",
                        extra={"user_id": user_id},
                    )
                    disconnected.append(websocket)

            # Clean up disconnected websockets
            for ws in disconnected:
                try:
                    self._connections[user_id].remove(ws)
                except ValueError:
                    pass

            if not self._connections[user_id]:
                del self._connections[user_id]

            logger.debug(
                f"Sent message to {sent_count}/{len(connections)} connections for user {user_id}",
                extra={
                    "user_id": user_id,
                    "sent_count": sent_count,
                    "total_connections": len(connections),
                },
            )

            return sent_count

    def get_connection_count(self, user_id: str) -> int:
        """Get the number of active connections for a user."""
        return len(self._connections.get(user_id, []))

    def get_total_connections(self) -> int:
        """Get the total number of active connections across all users."""
        return sum(len(conns) for conns in self._connections.values())
