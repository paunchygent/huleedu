from __future__ import annotations

from typing import Any, AsyncIterator, Protocol

from aiokafka import ConsumerRecord
from common_core.events.notification_events import TeacherNotificationRequestedV1


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


class KafkaConsumerProtocol(Protocol):
    """
    Protocol for Kafka consumer operations.
    """

    async def start(self) -> None:
        """Start the consumer."""
        ...

    async def stop(self) -> None:
        """Stop the consumer."""
        ...

    def __aiter__(self) -> AsyncIterator[ConsumerRecord]:
        """Iterate over messages."""
        ...

    async def commit(self) -> None:
        """Commit the current offset."""
        ...


class NotificationEventConsumerProtocol(Protocol):
    """
    Protocol for consuming teacher notification events from Kafka.
    This is the ONLY consumer the WebSocket service should have.
    """

    async def start_consumer(self) -> None:
        """
        Start consuming teacher notification events from Kafka.
        This should run indefinitely until stopped.
        """
        ...

    async def stop_consumer(self) -> None:
        """
        Stop the Kafka consumer gracefully.
        """
        ...

    async def process_message(self, msg: ConsumerRecord) -> bool:
        """
        Process a single Kafka message containing a teacher notification event.
        Returns True if message was processed successfully, False otherwise.
        """
        ...


class NotificationHandlerProtocol(Protocol):
    """
    Protocol for handling teacher notifications.
    This is a pure forwarder with NO business logic.
    """

    async def handle_teacher_notification(self, event: TeacherNotificationRequestedV1) -> None:
        """
        Handle TeacherNotificationRequestedV1 event and publish to Redis.
        The service trusts the teacher_id in the event (services are trusted).
        """
        ...
