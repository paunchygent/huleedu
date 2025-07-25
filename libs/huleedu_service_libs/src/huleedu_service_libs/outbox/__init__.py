"""
Transactional Outbox Pattern Library.

This module provides a generic, reusable implementation of the Transactional Outbox Pattern
for reliable event publishing across HuleEdu microservices. It ensures that database updates
and event publications are atomic, preventing data inconsistency when Kafka is unavailable.

Key Components:
- OutboxRepositoryProtocol: Interface for outbox storage operations
- EventOutbox: SQLAlchemy model for the event_outbox table
- PostgreSQLOutboxRepository: Default PostgreSQL implementation
- EventRelayWorker: Background worker that polls and publishes events
- OutboxProvider: Dishka provider for dependency injection

Usage:
    from huleedu_service_libs.outbox import (
        OutboxRepositoryProtocol,
        EventOutbox,
        PostgreSQLOutboxRepository,
        EventRelayWorker,
        OutboxProvider,
    )
"""

from __future__ import annotations

from .di import OutboxProvider
from .models import EventOutbox
from .protocols import (
    EventTypeMapperProtocol,
    OutboxEvent,
    OutboxRepositoryProtocol,
)
from .relay import EventRelayWorker
from .repository import PostgreSQLOutboxRepository

__all__ = [
    "OutboxRepositoryProtocol",
    "OutboxEvent",
    "EventTypeMapperProtocol",
    "EventOutbox",
    "PostgreSQLOutboxRepository",
    "EventRelayWorker",
    "OutboxProvider",
]