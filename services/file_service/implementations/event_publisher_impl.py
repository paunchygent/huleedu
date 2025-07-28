"""Event publisher implementation for File Service."""

from __future__ import annotations

import uuid

from common_core.events.envelope import EventEnvelope
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from huleedu_service_libs.error_handling import raise_outbox_storage_error
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol

from services.file_service.config import Settings
from services.file_service.protocols import EventPublisherProtocol

logger = create_service_logger("file_service.implementations.event_publisher")


class DefaultEventPublisher(EventPublisherProtocol):
    """Default implementation of EventPublisherProtocol with transactional outbox pattern."""

    def __init__(
        self,
        kafka_bus: KafkaPublisherProtocol,
        settings: Settings,
        redis_client: AtomicRedisClientProtocol,
        outbox_repository: OutboxRepositoryProtocol,
    ):
        self.kafka_bus = kafka_bus
        self.settings = settings
        self.redis_client = redis_client
        self.outbox_repository = outbox_repository

    async def publish_essay_content_provisioned(
        self,
        event_data: EssayContentProvisionedV1,
        correlation_id: uuid.UUID,
    ) -> None:
        """Publish EssayContentProvisionedV1 event via transactional outbox."""
        try:
            # Construct EventEnvelope
            from huleedu_service_libs.observability import inject_trace_context

            envelope = EventEnvelope[EssayContentProvisionedV1](
                event_type=self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC,
                source_service=self.settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=event_data,
                metadata={},
            )

            # Inject current trace context into the envelope metadata
            if envelope.metadata is not None:
                inject_trace_context(envelope.metadata)

            # Try immediate Kafka publishing first
            topic = self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC
            key = event_data.file_upload_id

            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )

            logger.info(
                "EssayContentProvisionedV1 event published directly to Kafka",
                extra={
                    "file_upload_id": event_data.file_upload_id,
                    "original_file_name": event_data.original_file_name,
                    "correlation_id": str(correlation_id),
                    "topic": topic,
                },
            )
            return  # Success - no outbox needed!

        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise

            logger.warning(
                "Kafka publish failed, falling back to outbox",
                extra={
                    "file_upload_id": event_data.file_upload_id,
                    "error": str(kafka_error),
                    "error_type": kafka_error.__class__.__name__,
                },
            )

        # Kafka failed - use outbox pattern as fallback
        aggregate_id = event_data.file_upload_id
        aggregate_type = "file_upload"
        topic = self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC

        # Store in outbox for reliable delivery
        try:
            await self._publish_to_outbox(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=topic,
                event_data=envelope,
                topic=topic,
                event_key=aggregate_id,
            )

            # Wake up the relay worker immediately
            await self._notify_relay_worker()

            logger.info(
                "EssayContentProvisionedV1 event stored in outbox and relay worker notified",
                extra={
                    "file_upload_id": event_data.file_upload_id,
                    "original_file_name": event_data.original_file_name,
                    "correlation_id": str(correlation_id),
                },
            )

        except Exception as e:
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_outbox_storage_error(
                    service="file_service",
                    operation="publish_essay_content_provisioned",
                    message=f"{e.__class__.__name__}: {str(e)}",
                    correlation_id=correlation_id,
                    aggregate_id=aggregate_id,
                    aggregate_type=aggregate_type,
                    event_type=topic,
                    topic=topic,
                    file_upload_id=event_data.file_upload_id,
                    original_file_name=event_data.original_file_name,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def publish_essay_validation_failed(
        self,
        event_data: EssayValidationFailedV1,
        correlation_id: uuid.UUID,
    ) -> None:
        """Publish EssayValidationFailedV1 event with immediate Kafka attempt
        and outbox fallback."""
        # Construct EventEnvelope
        from huleedu_service_libs.observability import inject_trace_context

        envelope = EventEnvelope[EssayValidationFailedV1](
            event_type=self.settings.ESSAY_VALIDATION_FAILED_TOPIC,
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id,
            data=event_data,
            metadata={},
        )

        # Inject current trace context into the envelope metadata
        if envelope.metadata is not None:
            inject_trace_context(envelope.metadata)

        # Try immediate Kafka publishing first
        topic = self.settings.ESSAY_VALIDATION_FAILED_TOPIC
        key = event_data.file_upload_id

        try:
            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )

            logger.info(
                "EssayValidationFailedV1 event published directly to Kafka",
                extra={
                    "file_upload_id": event_data.file_upload_id,
                    "original_file_name": event_data.original_file_name,
                    "correlation_id": str(correlation_id),
                    "topic": topic,
                },
            )
            return  # Success - no outbox needed!

        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise

            logger.warning(
                "Kafka publish failed, falling back to outbox",
                extra={
                    "file_upload_id": event_data.file_upload_id,
                    "error": str(kafka_error),
                    "error_type": kafka_error.__class__.__name__,
                },
            )

        # Kafka failed - use outbox pattern as fallback
        aggregate_id = event_data.file_upload_id
        aggregate_type = "file_upload"

        # Store in outbox for reliable delivery
        try:
            await self._publish_to_outbox(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=topic,
                event_data=envelope,
                topic=topic,
                event_key=aggregate_id,
            )

            # Wake up the relay worker immediately
            await self._notify_relay_worker()

            logger.info(
                "EssayValidationFailedV1 event stored in outbox and relay worker notified",
                extra={
                    "file_upload_id": event_data.file_upload_id,
                    "original_file_name": event_data.original_file_name,
                    "correlation_id": str(correlation_id),
                },
            )

        except Exception as e:
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_outbox_storage_error(
                    service="file_service",
                    operation="publish_essay_validation_failed",
                    message=f"{e.__class__.__name__}: {str(e)}",
                    correlation_id=correlation_id,
                    aggregate_id=aggregate_id,
                    aggregate_type=aggregate_type,
                    event_type=topic,
                    topic=topic,
                    file_upload_id=event_data.file_upload_id,
                    original_file_name=event_data.original_file_name,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def publish_batch_file_added_v1(
        self,
        event_data: BatchFileAddedV1,
        correlation_id: uuid.UUID,
    ) -> None:
        """Publish BatchFileAddedV1 event via transactional outbox and Redis."""
        try:
            # Construct EventEnvelope
            from huleedu_service_libs.observability import inject_trace_context

            envelope = EventEnvelope[BatchFileAddedV1](
                event_type=self.settings.BATCH_FILE_ADDED_TOPIC,
                source_service=self.settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=event_data,
                metadata={},
            )

            # Inject current trace context into the envelope metadata
            if envelope.metadata is not None:
                inject_trace_context(envelope.metadata)

            # Try immediate Kafka publishing first
            topic = self.settings.BATCH_FILE_ADDED_TOPIC
            key = event_data.batch_id

            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )

            logger.info(
                "BatchFileAddedV1 event published directly to Kafka",
                extra={
                    "batch_id": event_data.batch_id,
                    "file_upload_id": event_data.file_upload_id,
                    "filename": event_data.filename,
                    "correlation_id": str(correlation_id),
                    "topic": topic,
                },
            )

        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise

            logger.warning(
                "Kafka publish failed, falling back to outbox",
                extra={
                    "batch_id": event_data.batch_id,
                    "error": str(kafka_error),
                    "error_type": kafka_error.__class__.__name__,
                },
            )

            # Kafka failed - use outbox pattern as fallback
            aggregate_id = event_data.batch_id
            aggregate_type = "batch"
            topic = self.settings.BATCH_FILE_ADDED_TOPIC

            # Store in outbox for reliable delivery
            try:
                await self._publish_to_outbox(
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    event_type=topic,
                    event_data=envelope,
                    topic=topic,
                    event_key=aggregate_id,
                )

                # Wake up the relay worker immediately
                await self._notify_relay_worker()

                logger.info(
                    "BatchFileAddedV1 event stored in outbox and relay worker notified",
                    extra={
                        "batch_id": event_data.batch_id,
                        "file_upload_id": event_data.file_upload_id,
                        "filename": event_data.filename,
                        "correlation_id": str(correlation_id),
                    },
                )

            except Exception as e:
                if hasattr(e, "error_detail"):
                    raise
                else:
                    raise_outbox_storage_error(
                        service="file_service",
                        operation="publish_batch_file_added_v1",
                        message=f"{e.__class__.__name__}: {str(e)}",
                        correlation_id=correlation_id,
                        aggregate_id=aggregate_id,
                        aggregate_type=aggregate_type,
                        event_type=topic,
                        topic=topic,
                        batch_id=event_data.batch_id,
                        file_upload_id=event_data.file_upload_id,
                        filename=event_data.filename,
                        error_type=e.__class__.__name__,
                        error_details=str(e),
                    )

        # Redis publication continues separately (this is for real-time UI updates)
        try:
            # Publish to Redis for real-time updates (maintained as-is)
            await self._publish_file_event_to_redis(
                event_data.user_id,
                "batch_file_added",
                {
                    "batch_id": event_data.batch_id,
                    "file_upload_id": event_data.file_upload_id,
                    "filename": event_data.filename,
                    "timestamp": event_data.timestamp.isoformat(),
                },
            )

        except Exception as e:
            logger.error(f"Error publishing BatchFileAddedV1 event: {e}")
            raise

    async def publish_batch_file_removed_v1(
        self,
        event_data: BatchFileRemovedV1,
        correlation_id: uuid.UUID,
    ) -> None:
        """Publish BatchFileRemovedV1 event via transactional outbox and Redis."""
        try:
            # Construct EventEnvelope
            from huleedu_service_libs.observability import inject_trace_context

            envelope = EventEnvelope[BatchFileRemovedV1](
                event_type=self.settings.BATCH_FILE_REMOVED_TOPIC,
                source_service=self.settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=event_data,
                metadata={},
            )

            # Inject current trace context into the envelope metadata
            if envelope.metadata is not None:
                inject_trace_context(envelope.metadata)

            # Try immediate Kafka publishing first
            topic = self.settings.BATCH_FILE_REMOVED_TOPIC
            key = event_data.batch_id

            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )

            logger.info(
                "BatchFileRemovedV1 event published directly to Kafka",
                extra={
                    "batch_id": event_data.batch_id,
                    "file_upload_id": event_data.file_upload_id,
                    "filename": event_data.filename,
                    "correlation_id": str(correlation_id),
                    "topic": topic,
                },
            )

        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise

            logger.warning(
                "Kafka publish failed, falling back to outbox",
                extra={
                    "batch_id": event_data.batch_id,
                    "error": str(kafka_error),
                    "error_type": kafka_error.__class__.__name__,
                },
            )

            # Kafka failed - use outbox pattern as fallback
            aggregate_id = event_data.batch_id
            aggregate_type = "batch"
            topic = self.settings.BATCH_FILE_REMOVED_TOPIC

            # Store in outbox for reliable delivery
            try:
                await self._publish_to_outbox(
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    event_type=topic,
                    event_data=envelope,
                    topic=topic,
                    event_key=aggregate_id,
                )

                # Wake up the relay worker immediately
                await self._notify_relay_worker()

                logger.info(
                    "BatchFileRemovedV1 event stored in outbox and relay worker notified",
                    extra={
                        "batch_id": event_data.batch_id,
                        "file_upload_id": event_data.file_upload_id,
                        "filename": event_data.filename,
                        "correlation_id": str(correlation_id),
                    },
                )

            except Exception as e:
                if hasattr(e, "error_detail"):
                    raise
                else:
                    raise_outbox_storage_error(
                        service="file_service",
                        operation="publish_batch_file_removed_v1",
                        message=f"{e.__class__.__name__}: {str(e)}",
                        correlation_id=correlation_id,
                        aggregate_id=aggregate_id,
                        aggregate_type=aggregate_type,
                        event_type=topic,
                        topic=topic,
                        batch_id=event_data.batch_id,
                        file_upload_id=event_data.file_upload_id,
                        filename=event_data.filename,
                        error_type=e.__class__.__name__,
                        error_details=str(e),
                    )

        # Redis publication continues separately (this is for real-time UI updates)
        try:
            # Publish to Redis for real-time updates (maintained as-is)
            await self._publish_file_event_to_redis(
                event_data.user_id,
                "batch_file_removed",
                {
                    "batch_id": event_data.batch_id,
                    "file_upload_id": event_data.file_upload_id,
                    "filename": event_data.filename,
                    "timestamp": event_data.timestamp.isoformat(),
                },
            )

        except Exception as e:
            logger.error(f"Error publishing BatchFileRemovedV1 event: {e}")
            raise

    async def _publish_file_event_to_redis(
        self,
        user_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        """Publish file event to Redis for real-time UI notifications."""
        try:
            await self.redis_client.publish_user_notification(
                user_id=user_id, event_type=event_type, data=data
            )

            logger.info(
                f"Published {event_type} notification to Redis for user {user_id}",
                extra={"user_id": user_id, "event_type": event_type},
            )

        except Exception as e:
            logger.error(
                f"Error publishing {event_type} to Redis: {e}",
                extra={"user_id": user_id, "event_type": event_type},
                exc_info=True,
            )
            # Don't fail the entire event publishing if Redis fails

    async def _publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: EventEnvelope,
        topic: str,
        event_key: str | None = None,
    ) -> None:
        """
        Store event in outbox for reliable delivery (internal method).

        This implements the Transactional Outbox Pattern as a fallback mechanism
        when Kafka is unavailable.
        """
        # Serialize the envelope to JSON for storage
        serialized_data = event_data.model_dump(mode="json")

        # Store topic in the data for relay worker
        serialized_data["topic"] = topic

        # Store in outbox
        outbox_id = await self.outbox_repository.add_event(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            event_type=event_type,
            event_data=serialized_data,
            topic=topic,
            event_key=event_key,
        )

        logger.debug(
            "Event stored in outbox as fallback",
            extra={
                "outbox_id": str(outbox_id),
                "event_type": event_type,
                "aggregate_id": aggregate_id,
                "aggregate_type": aggregate_type,
            },
        )

    async def _notify_relay_worker(self) -> None:
        """Notify the relay worker that new events are available in the outbox."""
        try:
            # Use LPUSH to add a notification to the wake-up list
            # The relay worker will use BLPOP to wait for this
            await self.redis_client.lpush("outbox:wake:file_service", "1")
            logger.debug("Relay worker notified via Redis")
        except Exception as e:
            # Log but don't fail - the relay worker will still poll eventually
            logger.warning(
                "Failed to notify relay worker via Redis",
                extra={"error": str(e)},
            )
