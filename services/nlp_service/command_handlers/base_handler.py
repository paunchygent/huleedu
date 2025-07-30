"""Base protocol for NLP Service command handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from opentelemetry.trace import Span

import aiohttp
from aiokafka import ConsumerRecord
from common_core.events.envelope import EventEnvelope


class CommandHandlerProtocol(Protocol):
    """Base protocol for all NLP command handlers."""

    async def can_handle(self, event_type: str) -> bool:
        """Check if this handler can process the given event type.

        Args:
            event_type: The event type string to check

        Returns:
            True if this handler can process the event type, False otherwise
        """
        ...

    async def handle(
        self,
        msg: ConsumerRecord,
        envelope: EventEnvelope,
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
        span: "Span | None" = None,
    ) -> bool:
        """Process the command and return success status.

        Args:
            msg: The Kafka message to process
            envelope: Already parsed event envelope
            http_session: HTTP session for external service calls
            correlation_id: Correlation ID for tracking
            span: Optional span for tracing

        Returns:
            True if processing succeeded, False otherwise
        """
        ...
