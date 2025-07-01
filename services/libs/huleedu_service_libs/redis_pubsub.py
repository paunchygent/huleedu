"""
Redis Pub/Sub functionality for HuleEdu microservices.

Provides pub/sub operations for real-time notifications and WebSocket support.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("redis-pubsub")


class RedisPubSub:
    """Redis Pub/Sub functionality for real-time notifications."""

    def __init__(self, client: aioredis.Redis, client_id: str) -> None:
        self.client = client
        self.client_id = client_id

    async def publish(self, channel: str, message: str) -> int:
        """
        Publish a message to a Redis channel with proper error handling and logging.

        CRITICAL: This method enables the WebSocket backplane by allowing backend
        services to publish real-time updates to user-specific channels.

        Args:
            channel: The channel to publish to
            message: The message to publish

        Returns:
            Number of subscribers that received the message
        """
        try:
            # Publish message and get subscriber count
            receiver_count = await self.client.publish(channel, message)
            receiver_count = int(receiver_count)  # Ensure it's an integer

            logger.debug(
                f"Redis PUBLISH by '{self.client_id}': channel='{channel}', "
                f"message='{message[:75]}...', receivers={receiver_count}",
            )
            return receiver_count

        except Exception as e:
            logger.error(
                f"Error in Redis PUBLISH operation by '{self.client_id}' "
                f"for channel '{channel}': {e}",
                exc_info=True,
            )
            raise

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncGenerator[Any, None]:
        """
        Subscribe to a Redis channel with proper lifecycle management.

        CRITICAL: This method enables API Gateway instances to listen for
        user-specific real-time updates from backend services.

        Args:
            channel: The channel to subscribe to

        Yields:
            PubSub instance for receiving messages
        """
        pubsub = self.client.pubsub()
        try:
            await pubsub.subscribe(channel)
            logger.debug(f"Redis SUBSCRIBE by '{self.client_id}' to channel '{channel}'")
            yield pubsub
        except Exception as e:
            logger.error(
                f"Error in Redis SUBSCRIBE operation by '{self.client_id}' "
                f"for channel '{channel}': {e}",
                exc_info=True,
            )
            raise
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()  # Use aclose() instead of deprecated close()
                logger.debug(
                    f"Redis UNSUBSCRIBE cleanup by '{self.client_id}' from channel '{channel}'",
                )
            except Exception as e:
                logger.error(
                    f"Error during Redis UNSUBSCRIBE cleanup by '{self.client_id}': {e}",
                    exc_info=True,
                )
                # Don't re-raise cleanup errors

    def get_user_channel(self, user_id: str) -> str:
        """
        Generate standardized user-specific channel name.

        Args:
            user_id: The authenticated user's ID

        Returns:
            Standardized channel name for the user (e.g., "ws:user_123")
        """
        return f"ws:{user_id}"

    async def publish_user_notification(
        self, user_id: str, event_type: str, data: dict[str, Any]
    ) -> int:
        """
        Convenience method to publish structured notifications to user-specific channels.

        Args:
            user_id: The target user's ID
            event_type: The type of event (e.g., "batch_status_update")
            data: The event data payload

        Returns:
            Number of subscribers that received the notification
        """
        channel = self.get_user_channel(user_id)
        notification = {"event": event_type, "data": data}
        message = json.dumps(notification)
        return await self.publish(channel, message)
