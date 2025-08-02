"""
Kafka consumer for file management events in WebSocket Service.

Consumes file events from Kafka and publishes notifications to Redis
for real-time WebSocket delivery.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Awaitable, Callable
from uuid import uuid4

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

from aiokafka import AIOKafkaConsumer, ConsumerRecord
from aiokafka.errors import KafkaConnectionError
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from huleedu_service_libs.error_handling import (
    raise_connection_error,
    raise_initialization_failed,
)
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import extract_trace_context
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.websocket_service.config import Settings
from services.websocket_service.protocols import (
    FileEventConsumerProtocol,
    FileNotificationHandlerProtocol,
    KafkaConsumerProtocol,
)

logger = create_service_logger("websocket.file_event_consumer")


class FileEventConsumer(FileEventConsumerProtocol):
    """Kafka consumer for file management events."""

    def __init__(
        self,
        settings: Settings,
        notification_handler: FileNotificationHandlerProtocol,
        redis_client: AtomicRedisClientProtocol,
        kafka_consumer_factory: Callable[..., KafkaConsumerProtocol] | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        """Initialize the file event consumer."""
        self.settings = settings
        self.notification_handler = notification_handler
        self.redis_client = redis_client
        self.kafka_consumer_factory = kafka_consumer_factory or AIOKafkaConsumer
        self.tracer = tracer
        self.consumer: KafkaConsumerProtocol | None = None
        self.should_stop = False

        # Topics to consume
        self.topics = [
            self.settings.BATCH_FILE_ADDED_TOPIC,
            self.settings.BATCH_FILE_REMOVED_TOPIC,
        ]

        # Create idempotency configuration
        idempotency_config = IdempotencyConfig(
            service_name="websocket-service",
            enable_debug_logging=True,
        )

        # Create idempotent message processor
        @idempotent_consumer(redis_client=redis_client, config=idempotency_config)
        async def process_message_idempotently(
            msg: object, *, confirm_idempotency: Callable[[], Awaitable[None]]
        ) -> bool | None:
            result = await self.process_message(msg)
            await confirm_idempotency()
            return result

        self.process_message_idempotently = process_message_idempotently

    async def start_consumer(self) -> None:
        """Start consuming file events from Kafka."""
        try:
            logger.info(
                "Starting Kafka consumer for file events",
                extra={
                    "topics": self.topics,
                    "group_id": self.settings.KAFKA_CONSUMER_GROUP,
                },
            )

            self.consumer = self.kafka_consumer_factory(
                *self.topics,
                bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id=self.settings.KAFKA_CONSUMER_GROUP,
                client_id=self.settings.KAFKA_CONSUMER_CLIENT_ID,
                enable_auto_commit=False,
                auto_offset_reset="earliest",
            )

            await self.consumer.start()
            logger.info("Kafka consumer started successfully")

            # Main consumption loop
            async for msg in self.consumer:
                if self.should_stop:
                    break

                try:
                    await self.process_message_idempotently(msg)
                    await self.consumer.commit()
                except Exception as e:
                    logger.error(
                        f"Error processing message: {e}",
                        exc_info=True,
                        extra={
                            "topic": msg.topic,
                            "partition": msg.partition,
                            "offset": msg.offset,
                        },
                    )
                    # Continue processing other messages

        except KafkaConnectionError as e:
            logger.error(f"Kafka connection error: {e}", exc_info=True)
            raise_connection_error(
                service="websocket_service",
                operation="kafka_consume",
                target="kafka",
                message=f"Failed to connect to Kafka: {str(e)}",
                correlation_id=uuid4(),
            )
        except Exception as e:
            logger.error(f"Unexpected error in consumer: {e}", exc_info=True)
            raise_initialization_failed(
                service="websocket_service",
                operation="start_consumer",
                component="kafka_consumer",
                message=f"Failed to initialize Kafka consumer: {str(e)}",
                correlation_id=uuid4(),
            )
        finally:
            if self.consumer:
                await self.consumer.stop()

    async def stop_consumer(self) -> None:
        """Stop the Kafka consumer gracefully."""
        logger.info("Stopping Kafka consumer")
        self.should_stop = True
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped")

    async def process_message(self, msg: ConsumerRecord) -> bool:
        """Process a single Kafka message containing file events."""
        try:
            # Parse raw message bytes to EventEnvelope
            raw_message = msg.value.decode("utf-8")
            envelope_data = json.loads(raw_message)  # Still need for trace context extraction

            # Extract trace context if present
            if envelope_data.get("metadata"):
                extract_trace_context(envelope_data["metadata"])

            logger.info(
                f"Processing file event: {envelope_data['event_type']}",
                extra={
                    "event_id": envelope_data.get("event_id"),
                    "correlation_id": envelope_data.get("correlation_id"),
                },
            )

            # Route to appropriate handler based on event type
            if envelope_data["event_type"] == "huleedu.file.batch.file.added.v1":
                # Create event from the data field
                added_event = BatchFileAddedV1(**envelope_data["data"])
                await self.notification_handler.handle_batch_file_added(added_event)
            elif envelope_data["event_type"] == "huleedu.file.batch.file.removed.v1":
                # Create event from the data field
                removed_event = BatchFileRemovedV1(**envelope_data["data"])
                await self.notification_handler.handle_batch_file_removed(removed_event)
            else:
                logger.warning(
                    f"Unknown event type: {envelope_data['event_type']}",
                    extra={"event_id": envelope_data.get("event_id")},
                )
                return False

            logger.info(
                f"Successfully processed file event: {envelope_data['event_type']}",
                extra={"event_id": envelope_data.get("event_id")},
            )
            return True

        except Exception as e:
            logger.error(
                f"Error processing file event: {e}",
                exc_info=True,
                extra={
                    "topic": msg.topic,
                    "partition": msg.partition,
                    "offset": msg.offset,
                },
            )
            return False
