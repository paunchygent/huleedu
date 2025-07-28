from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import WebSocket
from huleedu_service_libs.error_handling import (
    raise_connection_error,
    raise_external_service_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.websocket_service.protocols import WebSocketManagerProtocol

logger = create_service_logger("websocket.message_listener")


class RedisMessageListener:
    """
    Listens to Redis pub/sub channels and forwards messages to WebSocket connections.
    """

    def __init__(
        self,
        redis_client: AtomicRedisClientProtocol,
        websocket_manager: WebSocketManagerProtocol,
    ):
        self._redis_client = redis_client
        self._websocket_manager = websocket_manager

    async def start_listening(self, user_id: str, websocket: WebSocket) -> None:
        """
        Start listening for messages for a specific user and forward them to the WebSocket.
        This handles the entire lifecycle of the listener.
        """
        channel_name = self._redis_client.get_user_channel(user_id)
        logger.info(
            f"Starting Redis listener for user {user_id} on channel {channel_name}",
            extra={"user_id": user_id, "channel": channel_name},
        )

        listener_task = None
        try:
            # Create the listener task
            listener_task = asyncio.create_task(self._redis_listener(user_id, websocket))

            # Wait for the WebSocket to disconnect
            await websocket.receive_text()

        except Exception as e:
            logger.info(
                f"WebSocket disconnected for user {user_id}: {type(e).__name__}",
                extra={"user_id": user_id},
            )
        finally:
            # Clean up the listener task
            if listener_task and not listener_task.done():
                logger.info(
                    f"Cancelling Redis listener for user {user_id}",
                    extra={"user_id": user_id},
                )
                listener_task.cancel()
                try:
                    await listener_task
                except asyncio.CancelledError:
                    pass

    async def _redis_listener(self, user_id: str, websocket: WebSocket) -> None:
        """Internal method to listen to Redis and forward messages."""
        channel_name = self._redis_client.get_user_channel(user_id)
        correlation_id = uuid4()

        try:
            async with self._redis_client.subscribe(channel_name) as pubsub:
                while True:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message and message.get("type") == "message":
                        data = message["data"].decode("utf-8")
                        logger.debug(
                            f"Forwarding message to user {user_id}: {data[:100]}...",
                            extra={"user_id": user_id},
                        )

                        # Send message through the WebSocket manager
                        await self._websocket_manager.send_message_to_user(user_id, data)

                    # Yield control to allow other tasks to run
                    await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            # Expected when the client disconnects
            logger.info(
                f"Redis listener cancelled for user {user_id}",
                extra={"user_id": user_id},
            )
            raise
        except ConnectionError as e:
            logger.error(
                f"Redis connection error for user {user_id}: {e}",
                exc_info=True,
                extra={"user_id": user_id},
            )
            raise_connection_error(
                service="websocket_service",
                operation="redis_subscribe",
                target="redis",
                message=f"Redis connection failed: {str(e)}",
                correlation_id=correlation_id,
            )
        except Exception as e:
            logger.error(
                f"Unexpected error in Redis listener for user {user_id}: {e}",
                exc_info=True,
                extra={"user_id": user_id},
            )
            # Close the WebSocket on unexpected errors
            await websocket.close(code=1011)  # Internal error
            raise_external_service_error(
                service="websocket_service",
                operation="redis_listener",
                external_service="redis",
                message=f"Unexpected error in Redis listener: {str(e)}",
                correlation_id=correlation_id,
            )
        finally:
            logger.info(
                f"Redis listener for user {user_id} is shutting down",
                extra={"user_id": user_id},
            )
