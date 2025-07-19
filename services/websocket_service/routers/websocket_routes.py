from __future__ import annotations

import time

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from huleedu_service_libs.logging_utils import create_service_logger

from services.websocket_service.metrics import WebSocketMetrics
from services.websocket_service.protocols import (
    JWTValidatorProtocol,
    MessageListenerProtocol,
    WebSocketManagerProtocol,
)

router = APIRouter()
logger = create_service_logger("websocket.routes")


@router.websocket("/")
@inject
async def websocket_endpoint(
    websocket: WebSocket,
    jwt_validator: FromDishka[JWTValidatorProtocol],
    websocket_manager: FromDishka[WebSocketManagerProtocol],
    message_listener: FromDishka[MessageListenerProtocol],
    metrics: FromDishka[WebSocketMetrics],
    token: str = Query(..., description="JWT token for authentication"),
) -> None:
    """
    Main WebSocket endpoint for real-time notifications.

    Authentication is performed via JWT token passed as query parameter.
    Each user can have multiple concurrent connections up to the configured limit.
    """
    start_time = time.time()
    user_id = None

    try:
        # Validate JWT token
        user_id = await jwt_validator.validate_token(token)
        if not user_id:
            logger.warning("WebSocket connection rejected: invalid token")
            metrics.jwt_validation_total.labels(result="invalid").inc()
            metrics.websocket_connections_total.labels(status="rejected").inc()
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
            return

        metrics.jwt_validation_total.labels(result="success").inc()

        # Accept the WebSocket connection
        await websocket.accept()
        metrics.websocket_connections_total.labels(status="accepted").inc()

        # Register the connection
        await websocket_manager.connect(websocket, user_id)
        metrics.websocket_active_connections.labels(user_id=user_id).inc()

        logger.info(
            f"WebSocket connection established for user {user_id}",
            extra={
                "user_id": user_id,
                "active_connections": websocket_manager.get_connection_count(user_id),
            },
        )

        # Start listening for Redis messages
        await message_listener.start_listening(user_id, websocket)

    except WebSocketDisconnect:
        logger.info(
            f"WebSocket disconnected by client for user {user_id}",
            extra={"user_id": user_id},
        )
    except Exception as e:
        logger.error(
            f"Unexpected error in WebSocket endpoint for user {user_id}: {e}",
            exc_info=True,
            extra={"user_id": user_id},
        )
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
    finally:
        # Clean up
        if user_id:
            await websocket_manager.disconnect(websocket, user_id)
            metrics.websocket_active_connections.labels(user_id=user_id).dec()

            # Record connection duration
            duration = time.time() - start_time
            metrics.websocket_connection_duration_seconds.observe(duration)

            logger.info(
                f"WebSocket connection closed for user {user_id}",
                extra={
                    "user_id": user_id,
                    "duration_seconds": duration,
                    "remaining_connections": websocket_manager.get_connection_count(user_id),
                },
            )

        metrics.websocket_connections_total.labels(status="closed").inc()
