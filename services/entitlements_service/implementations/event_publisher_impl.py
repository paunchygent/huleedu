"""
Event Publisher implementation for Entitlements Service.

This module implements the EventPublisherProtocol for publishing domain events
from credit operations using the transactional outbox pattern.
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from common_core import (
    CreditBalanceChangedV1,
    EventEnvelope,
    ProcessingEvent,
    RateLimitExceededV1,
    SubjectRefV1,
    UsageRecordedV1,
    topic_name,
)
from common_core.entitlements_models import SubjectType

from services.entitlements_service.implementations.outbox_manager import OutboxManager
from services.entitlements_service.protocols import EventPublisherProtocol

if TYPE_CHECKING:
    from services.entitlements_service.config import Settings

logger = logging.getLogger(__name__)


class EventPublisherImpl(EventPublisherProtocol):
    """
    Implementation of EventPublisher using transactional outbox pattern.

    Publishes domain events from credit operations to ensure reliable delivery
    and maintain audit trails across the system.
    """

    def __init__(
        self,
        outbox_manager: OutboxManager,
        settings: "Settings",
    ) -> None:
        """
        Initialize event publisher with dependencies.

        Args:
            outbox_manager: Manager for outbox pattern operations
            settings: Service configuration for event metadata
        """
        self.outbox_manager = outbox_manager
        self.settings = settings

    async def publish_credit_balance_changed(
        self,
        subject_type: str,
        subject_id: str,
        old_balance: int,
        new_balance: int,
        delta: int,
        correlation_id: str,
    ) -> None:
        """
        Publish credit balance changed event.

        Args:
            subject_type: Type of subject ("user" or "org")
            subject_id: ID of the subject
            old_balance: Previous credit balance
            new_balance: New credit balance after change
            delta: Amount of change (positive for credit, negative for debit)
            correlation_id: Correlation ID for tracing
        """
        logger.debug(
            f"Publishing credit balance changed: {subject_type}:{subject_id} "
            f"{old_balance} -> {new_balance} (delta: {delta})"
        )

        # subject_type is already the correct literal type
        subject_type_literal: SubjectType = subject_type  # type: ignore

        # Create the event payload
        event_data = CreditBalanceChangedV1(
            subject=SubjectRefV1(type=subject_type_literal, id=subject_id),
            delta=delta,
            new_balance=new_balance,
            reason="credit_operation",
            correlation_id=correlation_id,
        )

        # Create event envelope
        event_envelope = EventEnvelope[CreditBalanceChangedV1](
            event_id=uuid4(),
            event_type=topic_name(ProcessingEvent.ENTITLEMENTS_CREDIT_BALANCE_CHANGED),
            event_timestamp=datetime.now(timezone.utc),
            source_service=self.settings.SERVICE_NAME,
            correlation_id=uuid4(),
            data=event_data,
            metadata={
                "partition_key": subject_id,
                "subject_type": subject_type,
                "delta": str(delta),
            },
        )

        # Determine topic
        topic = topic_name(ProcessingEvent.ENTITLEMENTS_CREDIT_BALANCE_CHANGED)

        # Publish via outbox
        await self.outbox_manager.publish_to_outbox(
            aggregate_type=f"credit_balance_{subject_type}",
            aggregate_id=subject_id,
            event_type=topic_name(ProcessingEvent.ENTITLEMENTS_CREDIT_BALANCE_CHANGED),
            event_data=event_envelope,
            topic=topic,
        )

        logger.info(
            f"Credit balance changed event published: {subject_type}:{subject_id}",
            extra={
                "subject_type": subject_type,
                "subject_id": subject_id,
                "old_balance": old_balance,
                "new_balance": new_balance,
                "delta": delta,
                "correlation_id": correlation_id,
                "event_id": str(event_envelope.event_id),
            },
        )

    async def publish_rate_limit_exceeded(
        self,
        subject_id: str,
        metric: str,
        limit: int,
        current_count: int,
        window_seconds: int,
        correlation_id: str,
    ) -> None:
        """
        Publish rate limit exceeded event.

        Args:
            subject_id: ID of the subject that exceeded the limit
            metric: Metric that was rate limited
            limit: The configured rate limit
            current_count: Current usage count in the window
            window_seconds: Rate limit window in seconds
            correlation_id: Correlation ID for tracing
        """
        logger.debug(
            f"Publishing rate limit exceeded: {subject_id} for {metric} "
            f"({current_count}/{limit} in {window_seconds}s)"
        )

        # Create the event payload
        event_data = RateLimitExceededV1(
            subject=SubjectRefV1(type="user", id=subject_id),
            metric=metric,
            limit=limit,
            window_seconds=window_seconds,
            correlation_id=correlation_id,
        )

        # Create event envelope
        event_envelope = EventEnvelope[RateLimitExceededV1](
            event_id=uuid4(),
            event_type=topic_name(ProcessingEvent.ENTITLEMENTS_RATE_LIMIT_EXCEEDED),
            event_timestamp=datetime.now(timezone.utc),
            source_service=self.settings.SERVICE_NAME,
            correlation_id=uuid4(),
            data=event_data,
            metadata={
                "partition_key": subject_id,
                "metric": metric,
                "limit": str(limit),
                "current_count": str(current_count),
            },
        )

        # Determine topic
        topic = topic_name(ProcessingEvent.ENTITLEMENTS_RATE_LIMIT_EXCEEDED)

        # Publish via outbox
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="rate_limit_bucket",
            aggregate_id=subject_id,
            event_type=topic_name(ProcessingEvent.ENTITLEMENTS_RATE_LIMIT_EXCEEDED),
            event_data=event_envelope,
            topic=topic,
        )

        logger.warning(
            f"Rate limit exceeded event published: {subject_id} for {metric}",
            extra={
                "subject_id": subject_id,
                "metric": metric,
                "limit": limit,
                "current_count": current_count,
                "window_seconds": window_seconds,
                "correlation_id": correlation_id,
                "event_id": str(event_envelope.event_id),
            },
        )

    async def publish_usage_recorded(
        self,
        subject_type: str,
        subject_id: str,
        metric: str,
        amount: int,
        correlation_id: str,
    ) -> None:
        """
        Publish usage recorded event.

        Args:
            subject_type: Type of subject ("user" or "org")
            subject_id: ID of the subject
            metric: Operation metric name
            amount: Amount of usage recorded
            correlation_id: Correlation ID for tracing
        """
        logger.debug(
            f"Publishing usage recorded: {subject_type}:{subject_id} used {amount} of {metric}"
        )

        # subject_type is already the correct literal type
        subject_type_literal: SubjectType = subject_type  # type: ignore

        # Current time for period boundaries (simplistic approach)
        now = datetime.now(timezone.utc)

        # Create the event payload
        event_data = UsageRecordedV1(
            subject=SubjectRefV1(type=subject_type_literal, id=subject_id),
            metric=metric,
            amount=amount,
            period_start=now,
            period_end=now,
            correlation_id=correlation_id,
        )

        # Create event envelope
        event_envelope = EventEnvelope[UsageRecordedV1](
            event_id=uuid4(),
            event_type=topic_name(ProcessingEvent.ENTITLEMENTS_USAGE_RECORDED),
            event_timestamp=now,
            source_service=self.settings.SERVICE_NAME,
            correlation_id=uuid4(),
            data=event_data,
            metadata={
                "partition_key": subject_id,
                "subject_type": subject_type,
                "metric": metric,
                "amount": str(amount),
            },
        )

        # Determine topic
        topic = topic_name(ProcessingEvent.ENTITLEMENTS_USAGE_RECORDED)

        # Publish via outbox
        await self.outbox_manager.publish_to_outbox(
            aggregate_type=f"usage_{subject_type}",
            aggregate_id=subject_id,
            event_type=topic_name(ProcessingEvent.ENTITLEMENTS_USAGE_RECORDED),
            event_data=event_envelope,
            topic=topic,
        )

        logger.info(
            f"Usage recorded event published: {subject_type}:{subject_id} used {amount} {metric}",
            extra={
                "subject_type": subject_type,
                "subject_id": subject_id,
                "metric": metric,
                "amount": amount,
                "correlation_id": correlation_id,
                "event_id": str(event_envelope.event_id),
            },
        )
