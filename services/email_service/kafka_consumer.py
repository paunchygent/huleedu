"""Kafka consumer for Email Service.

This module provides Kafka message consumption with idempotency guarantees
following established patterns for reliable event processing.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError
from common_core.emailing_models import NotificationEmailRequestedV1
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from huleedu_service_libs.kafka_client import KAFKA_BOOTSTRAP_SERVERS
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol

if TYPE_CHECKING:
    from services.email_service.config import Settings
    from services.email_service.event_processor import EmailEventProcessor

logger = create_service_logger("email_service.kafka_consumer")


class EmailKafkaConsumer:
    """Kafka consumer for email processing events.

    Processes NotificationEmailRequestedV1 events with idempotency guarantees
    and proper error handling following service patterns.
    """

    def __init__(
        self,
        settings: Settings,
        event_processor: EmailEventProcessor,
        redis_client: RedisClientProtocol,
    ) -> None:
        """Initialize with injected dependencies."""
        self.settings = settings
        self.event_processor = event_processor
        self.redis_client = redis_client
        self.consumer: AIOKafkaConsumer | None = None
        self.should_stop = False

        # Consumer configuration
        self.topics = [topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED)]

        # Create idempotent message processor
        config = IdempotencyConfig(
            service_name="email-service",
            default_ttl=86400,  # 24 hours for email processing
            enable_debug_logging=True,
        )

        # Processor for email request messages
        @idempotent_consumer(redis_client=redis_client, config=config)
        async def process_email_request_idempotently(
            msg: Any, *, confirm_idempotency: Callable[[], Awaitable[None]]
        ) -> bool | None:
            result = await self._process_message(msg)
            await confirm_idempotency()  # Confirm after successful processing
            return result

        self._process_email_request_idempotently = process_email_request_idempotently

    async def start_consumer(self) -> None:
        """Start the Kafka consumer and begin processing messages."""
        logger.info("Starting email service Kafka consumer")

        # Create Kafka consumer
        self.consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id="email_service_consumer",
            auto_offset_reset="latest",
            enable_auto_commit=False,
            max_poll_records=1,  # Process one at a time for consistency
            session_timeout_ms=45000,
        )

        try:
            await self.consumer.start()
            logger.info(
                "Email service Kafka consumer started",
                extra={
                    "topics": self.topics,
                    "group_id": "email_service_consumer",
                },
            )

            # Start message processing loop
            await self._process_messages()

        except asyncio.CancelledError:
            logger.info("Kafka consumer task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in Email service Kafka consumer: {e}", exc_info=True)
            raise
        finally:
            await self.stop_consumer()

    async def stop_consumer(self) -> None:
        """Stop the Kafka consumer gracefully."""
        self.should_stop = True
        if self.consumer:
            try:
                await self.consumer.stop()
                logger.info("Email service Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping Email service Kafka consumer: {e}")
            finally:
                self.consumer = None

    async def _process_messages(self) -> None:
        """Main message processing loop."""
        if not self.consumer:
            return

        logger.info("Starting Email service message processing loop")

        while not self.should_stop:
            try:
                async for msg in self.consumer:
                    if self.should_stop:
                        break

                    try:
                        result = await self._process_email_request_idempotently(msg)

                        if result is not None:
                            # Only commit if not a skipped duplicate
                            if result:
                                await self.consumer.commit()
                                logger.debug(
                                    "Message committed: %s:%s:%s",
                                    msg.topic,
                                    msg.partition,
                                    msg.offset,
                                )
                            else:
                                logger.warning(
                                    f"Message processing failed, not committing: "
                                    f"{msg.topic}:{msg.partition}:{msg.offset}",
                                )
                        else:
                            # Message was a duplicate and skipped
                            logger.info(
                                f"Duplicate message skipped, not committing offset: "
                                f"{msg.topic}:{msg.partition}:{msg.offset}",
                            )

                    except Exception as e:
                        logger.error(f"Error processing message: {e}", exc_info=True)

            except KafkaConnectionError as kce:
                logger.error(f"Kafka connection error: {kce}", exc_info=True)
                if self.should_stop:
                    break
                await asyncio.sleep(5)  # Wait before retry
            except asyncio.CancelledError:
                logger.info("Message consumption cancelled")
                break
            except Exception as e:
                logger.error(f"Error in message processing loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying

        logger.info("Email service message processing loop has finished")

    async def _process_message(self, msg: Any) -> bool:
        """Process individual Kafka message.

        Args:
            msg: Kafka consumer record to process

        Returns:
            True if processing succeeded, False otherwise
        """
        logger.debug(f"Processing message from {msg.topic}:{msg.partition}:{msg.offset}")

        try:
            # Parse event envelope
            envelope = EventEnvelope[NotificationEmailRequestedV1].model_validate_json(msg.value)

            # Validate the data field as NotificationEmailRequestedV1
            email_request = NotificationEmailRequestedV1.model_validate(envelope.data)

            logger.info(
                f"Processing email notification request: {email_request.message_id} "
                f"(correlation_id: {email_request.correlation_id})"
            )

            # Process the email request
            await self.event_processor.process_email_request(email_request)

            logger.info(f"Successfully processed email request: {email_request.message_id}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to process email notification request: {e}",
                exc_info=True,
            )
            return False
