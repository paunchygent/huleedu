"""Kafka consumer for Email Service.

This module provides Kafka message consumption with idempotency guarantees
following established patterns for reliable event processing.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from aiokafka import ConsumerRecord
from common_core.emailing_models import NotificationEmailRequestedV1
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.redis_client import RedisClient

if TYPE_CHECKING:
    from services.email_service.config import Settings

logger = create_service_logger("email_service.kafka_consumer")


class EmailKafkaConsumer:
    """Kafka consumer for email processing events.

    Processes NotificationEmailRequestedV1 events with idempotency guarantees
    and proper error handling following service patterns.
    """

    def __init__(
        self,
        kafka_bus: KafkaBus,
        redis_client: RedisClient,
        settings: Settings,
    ):
        self.kafka_bus = kafka_bus
        self.redis_client = redis_client
        self.settings = settings

        # Consumer configuration
        self.group_id = "email_service_consumer"
        self.topics = [topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED)]

        # Idempotency configuration
        self.idempotency_config = IdempotencyConfig(
            ttl_seconds=86400,  # 24 hours
            key_prefix="email_service",
        )

        # Consumer state
        self.should_stop = False
        # Event processor will be injected via DI container

    async def start_consumer(self) -> None:
        """Start the Kafka consumer loop.

        Consumes messages from configured topics with manual commit strategy
        for reliability and proper error handling.
        """
        logger.info("Starting email service Kafka consumer")
        logger.info(f"Subscribed topics: {self.topics}")
        logger.info(f"Consumer group: {self.group_id}")

        try:
            consumer = await self.kafka_bus.get_consumer(
                group_id=self.group_id,
                topics=self.topics,
                enable_auto_commit=False,  # Manual commits for reliability
            )

            async for msg in consumer:
                if self.should_stop:
                    logger.info("Consumer stop requested, breaking from message loop")
                    break

                try:
                    await self.handle_message(msg)
                    await consumer.commit()

                except Exception as e:
                    logger.error(
                        f"Error processing message from {msg.topic}:{msg.partition}:{msg.offset}: {e}",
                        exc_info=True,
                    )
                    # Continue processing - individual message failures should not stop consumer
                    await consumer.commit()  # Still commit to avoid reprocessing

            logger.info("Kafka consumer loop ended")

        except Exception as e:
            logger.critical(f"Fatal error in Kafka consumer: {e}", exc_info=True)
            raise

    @idempotent_consumer
    async def handle_message(self, msg: ConsumerRecord) -> None:
        """Handle individual Kafka messages with idempotency.

        Args:
            msg: Kafka consumer record to process

        Note:
            @idempotent_consumer decorator automatically provides deduplication
            based on message key and offset for reliability.
        """
        logger.debug(f"Processing message from {msg.topic}:{msg.partition}:{msg.offset}")

        # Get event processor from DI container via AsyncCurrentContainer
        from dishka import AsyncCurrentContainer

        from services.email_service.event_processor import EmailEventProcessor

        container = AsyncCurrentContainer()
        async with container() as request_container:
            event_processor = await request_container.get(EmailEventProcessor)

        try:
            # Parse event envelope
            envelope = EventEnvelope[NotificationEmailRequestedV1].model_validate_json(msg.value)

            logger.info(
                f"Processing email notification request: {envelope.data.message_id} "
                f"(correlation_id: {envelope.data.correlation_id})"
            )

            # Process the email request
            await event_processor.process_email_request(envelope.data)

            logger.info(f"Successfully processed email request: {envelope.data.message_id}")

        except Exception as e:
            logger.error(
                f"Failed to process email notification request: {e}",
                exc_info=True,
            )
            raise

    async def stop_consumer(self) -> None:
        """Stop the Kafka consumer gracefully.

        Sets stop flag to break from consumer loop and allows for graceful shutdown.
        """
        logger.info("Stopping email service Kafka consumer")
        self.should_stop = True

        # Give consumer loop time to see stop flag
        await asyncio.sleep(0.1)
