"""
Shared OutboxManager implementation for all HuleEdu services.

This module provides a unified OutboxManager that eliminates the need for
service-specific implementations and adds support for headers and deterministic
partition keys as outlined in EVENT_PUBLISHING_IMPROVEMENTS.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from common_core.events.envelope import EventEnvelope

from huleedu_service_libs.error_handling.factories import raise_external_service_error
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.outbox.protocols import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import (
    AtomicRedisClientProtocol,
)

logger = create_service_logger("shared.outbox_manager")


class OutboxManager:
    """
    Shared OutboxManager for reliable event publishing with headers support.

    Provides the transactional outbox pattern for atomic consistency between
    business operations and event publishing, with support for:
    - Kafka message headers for idempotency and tracing
    - Deterministic partition keys for event ordering
    - Redis-based relay worker notifications
    - Comprehensive error handling with correlation context

    This implementation replaces all service-specific OutboxManager copies
    to ensure consistency and reduce maintenance overhead.
    """

    def __init__(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol | None = None,
        service_name: str = "unknown_service",
    ) -> None:
        """
        Initialize OutboxManager with required dependencies.

        Args:
            outbox_repository: Repository for outbox persistence
            redis_client: Optional Redis client for relay worker notifications
            service_name: Name of the service for logging and error context
        """
        self.outbox_repository = outbox_repository
        self.redis_client = redis_client
        self.service_name = service_name

    async def publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: EventEnvelope[Any],
        topic: str,
        message_key: str | None = None,
        headers: dict[str, str] | None = None,
        session: Any | None = None,  # AsyncSession | None
    ) -> None:
        """
        Store event in outbox for reliable delivery with headers support.

        This implements the TRUE OUTBOX PATTERN for transactional safety,
        ensuring events are stored atomically with business data and
        published asynchronously by the relay worker.

        Args:
            aggregate_type: Type of aggregate (e.g., "cj_batch", "essay")
            aggregate_id: ID of the aggregate that produced the event
            event_type: Type of event being published
            event_data: Complete event envelope to publish
            topic: Kafka topic to publish to
            message_key: Optional partition key for deterministic routing
            headers: Optional Kafka headers for idempotency/tracing
            session: Optional AsyncSession to use for transaction sharing

        Raises:
            HuleEduError: If outbox repository is not configured or storage fails
        """
        if not self.outbox_repository:
            raise_external_service_error(
                service=self.service_name,
                operation="publish_to_outbox",
                external_service="outbox_repository",
                message="Outbox repository not configured for transactional publishing",
                correlation_id=getattr(
                    event_data, "correlation_id", UUID("00000000-0000-0000-0000-000000000000")
                ),
                aggregate_id=aggregate_id,
                event_type=event_type,
            )

        try:
            # Validate event envelope structure
            if not hasattr(event_data, "model_dump"):
                raise ValueError(
                    f"OutboxManager expects Pydantic EventEnvelope, got {type(event_data)}"
                )

            # Serialize the envelope to JSON for storage
            serialized_data = event_data.model_dump(mode="json")

            # Add topic and headers to serialized data for relay worker
            serialized_data["topic"] = topic
            if headers:
                serialized_data["headers"] = headers

            # Determine partition key - use provided or fallback to aggregate_id
            partition_key = message_key or aggregate_id
            if hasattr(event_data, "metadata") and event_data.metadata:
                partition_key = event_data.metadata.get("partition_key", partition_key)

            # Create standard headers if not provided
            standard_headers = self._create_standard_headers(event_data, headers)

            # Store in outbox with headers
            outbox_id = await self.outbox_repository.add_event(
                aggregate_id=aggregate_id,
                aggregate_type=aggregate_type,
                event_type=event_type,
                event_data=serialized_data,
                topic=topic,
                event_key=partition_key,
                session=session,
            )

            logger.debug(
                "Event stored in outbox for transactional safety",
                extra={
                    "outbox_id": str(outbox_id),
                    "event_type": event_type,
                    "aggregate_id": aggregate_id,
                    "aggregate_type": aggregate_type,
                    "topic": topic,
                    "partition_key": partition_key,
                    "headers": standard_headers,
                    "correlation_id": str(getattr(event_data, "correlation_id", "unknown")),
                    "service": self.service_name,
                },
            )

            # Wake up the relay worker immediately if Redis available
            if self.redis_client:
                await self._notify_relay_worker()

        except Exception as e:
            # Re-raise HuleEduError as-is, wrap others with proper context
            if hasattr(e, "error_detail"):
                raise
            else:
                # Extract correlation ID for error context
                error_correlation_id = UUID("00000000-0000-0000-0000-000000000000")
                if hasattr(event_data, "correlation_id"):
                    error_correlation_id = event_data.correlation_id
                elif isinstance(event_data, dict):
                    try:
                        error_correlation_id = UUID(
                            str(
                                event_data.get(
                                    "correlation_id", "00000000-0000-0000-0000-000000000000"
                                )
                            )
                        )
                    except (ValueError, TypeError):
                        pass  # Use default UUID

                raise_external_service_error(
                    service=self.service_name,
                    operation="publish_to_outbox",
                    external_service="outbox_repository",
                    message=f"Failed to store event in outbox: {e.__class__.__name__}",
                    correlation_id=error_correlation_id,
                    aggregate_id=aggregate_id,
                    event_type=event_type,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    def _create_standard_headers(
        self,
        event_data: EventEnvelope[Any],
        provided_headers: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """
        Create standard Kafka headers for event publishing.

        Args:
            event_data: Event envelope containing metadata
            provided_headers: Optional headers provided by caller

        Returns:
            Dictionary of standard headers including event_id, trace_id, etc.
        """
        headers = provided_headers.copy() if provided_headers else {}

        # Add standard headers if not already provided
        if "event_id" not in headers:
            headers["event_id"] = str(getattr(event_data, "event_id", uuid4()))

        if "trace_id" not in headers:
            headers["trace_id"] = str(getattr(event_data, "correlation_id", uuid4()))

        if "schema_version" not in headers:
            headers["schema_version"] = str(getattr(event_data, "schema_version", 1))

        if "occurred_at" not in headers:
            timestamp = getattr(event_data, "event_timestamp", datetime.now(UTC))
            headers["occurred_at"] = (
                timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)
            )

        if "content_type" not in headers:
            headers["content_type"] = "application/json"

        if "source_service" not in headers:
            headers["source_service"] = getattr(event_data, "source_service", self.service_name)

        if "event_type" not in headers:
            headers["event_type"] = getattr(event_data, "event_type", "unknown")

        return headers

    async def _notify_relay_worker(self) -> None:
        """
        Notify the relay worker that new events are available for processing.

        Uses Redis pub/sub to wake up the relay worker immediately rather than
        waiting for the next polling interval.
        """
        if not self.redis_client:
            return

        try:
            wake_key = f"outbox:wake:{self.service_name}"
            await self.redis_client.lpush(wake_key, "wake")

            logger.debug(
                "Relay worker notification sent",
                extra={
                    "wake_key": wake_key,
                    "service": self.service_name,
                },
            )
        except Exception as e:
            # Don't fail the outbox operation if Redis notification fails
            logger.warning(
                f"Failed to notify relay worker: {e}",
                extra={
                    "service": self.service_name,
                    "error_type": type(e).__name__,
                },
            )


def resolve_partition_key(
    event_type: str,
    aggregate_id: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    Resolve deterministic partition key based on event type and context.

    This function implements the partition key strategy from EVENT_PUBLISHING_IMPROVEMENTS.md:
    - CJ Assessment: Use cj_assessment_job_id
    - Spellcheck/NLP: Use batch_id
    - Student Matching: Use batch_id
    - ELS State Events: Use entity_ref or essay_id

    Args:
        event_type: The event type being published
        aggregate_id: Default aggregate identifier
        metadata: Optional event metadata containing specific IDs

    Returns:
        Deterministic partition key for Kafka message routing
    """
    if not metadata:
        metadata = {}

    # CJ Assessment events use job ID for result grouping
    if "assessment.result" in event_type or "cj_assessment" in event_type:
        return metadata.get("cj_assessment_job_id", aggregate_id)

    # Batch processing events use batch_id for ordering
    if "batch." in event_type or "spellcheck" in event_type or "nlp" in event_type:
        return metadata.get("batch_id", aggregate_id)

    # Student matching events use batch_id for grouping
    if "student" in event_type or "matching" in event_type:
        return metadata.get("batch_id", aggregate_id)

    # ELS events use entity reference for essay-level ordering
    if "essay." in event_type or "els." in event_type:
        return metadata.get("entity_ref", metadata.get("essay_id", aggregate_id))

    # Default to aggregate_id
    return aggregate_id
