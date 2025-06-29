from __future__ import annotations

import asyncio

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from .. import auth

router = APIRouter()
logger = create_service_logger("api_gateway.websocket_routes")


@router.websocket("/{client_id}")
@inject
async def websocket_status_endpoint(
    websocket: WebSocket,
    client_id: str,
    redis_client: FromDishka[AtomicRedisClientProtocol],
    user_id: str = Depends(auth.get_current_user_id),
):
    """
    Handles WebSocket connections for real-time status updates.

    This endpoint establishes a WebSocket connection, authenticates the user,
    and subscribes to a user-specific Redis channel for real-time event
    notifications. It uses a concurrent design with two tasks:
    1. A Redis listener that forwards messages from the channel to the WebSocket.
    2. A WebSocket listener that detects when the client disconnects.

    This ensures that resources are cleaned up promptly on disconnection.
    """
    if client_id != user_id:
        logger.warning(
            f"Unauthorized WebSocket connection attempt for client '{client_id}' by user '{user_id}'.",
            extra={"client_id": client_id, "user_id": user_id},
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    logger.info(f"WebSocket connection accepted for user '{user_id}'.", extra={"user_id": user_id})

    async def redis_listener():
        """Listens to a Redis channel and forwards messages to the WebSocket client."""
        channel_name = redis_client.get_user_channel(user_id)
        logger.info(
            f"Subscribing to Redis channel '{channel_name}' for user '{user_id}'.",
            extra={"user_id": user_id, "channel": channel_name},
        )
        try:
            async for pubsub in redis_client.subscribe(channel_name):
                while True:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message and message.get("type") == "message":
                        data = message["data"].decode("utf-8")
                        logger.debug(
                            f"Forwarding message to user '{user_id}': {data}",
                            extra={"user_id": user_id},
                        )
                        await websocket.send_text(data)
                    await asyncio.sleep(0.01)  # Yield control to allow other tasks to run
        except asyncio.CancelledError:
            # This is expected when the client disconnects
            logger.info(
                f"Redis listener task cancelled for user '{user_id}'.", extra={"user_id": user_id}
            )
        except Exception as e:
            logger.error(
                f"Error in Redis listener for user '{user_id}': {e}",
                exc_info=True,
                extra={"user_id": user_id},
            )
            # Attempt to close the websocket gracefully on unexpected errors
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        finally:
            logger.info(
                f"Redis listener for user '{user_id}' is shutting down.", extra={"user_id": user_id}
            )

    listener_task = asyncio.create_task(redis_listener())

    try:
        # Wait for the client to disconnect.
        # The `receive_text` call will block until a message is received or the connection is closed.
        await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected by client '{user_id}'.", extra={"user_id": user_id})
    finally:
        # Clean up the listener task.
        logger.info(f"Cancelling Redis listener for user '{user_id}'.", extra={"user_id": user_id})
        listener_task.cancel()
        # Wait for the task to acknowledge cancellation
        await asyncio.gather(listener_task, return_exceptions=True)
        logger.info(
            f"WebSocket connection for user '{user_id}' is fully closed.",
            extra={"user_id": user_id},
        )
