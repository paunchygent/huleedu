"""Kafka consumer for Identity Service internal event processing.

This module provides Kafka message consumption for Identity Service's own
events to bridge them to Email Service notifications through the orchestrator.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.identity_models import (
    EmailVerificationRequestedV1,
    PasswordResetRequestedV1,
    UserRegisteredV1,
)
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from huleedu_service_libs.kafka_client import KAFKA_BOOTSTRAP_SERVERS
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol

if TYPE_CHECKING:
    from services.identity_service.config import Settings
    from services.identity_service.notification_orchestrator import NotificationOrchestrator

logger = create_service_logger("identity_service.kafka_consumer")


class IdentityKafkaConsumer:
    """Kafka consumer for Identity Service internal event processing.

    Consumes Identity Service's own published events and routes them through
    the NotificationOrchestrator to bridge to Email Service notifications.
    """

    def __init__(
        self,
        settings: Settings,
        notification_orchestrator: NotificationOrchestrator,
        redis_client: RedisClientProtocol,
    ) -> None:
        """Initialize with injected dependencies."""
        self.settings = settings
        self.notification_orchestrator = notification_orchestrator
        self.redis_client = redis_client
        self.consumer: AIOKafkaConsumer | None = None
        self.should_stop = False

        # Consumer configuration - listen to Identity Service's own events
        self.topics = [
            topic_name(ProcessingEvent.IDENTITY_EMAIL_VERIFICATION_REQUESTED),
            topic_name(ProcessingEvent.IDENTITY_PASSWORD_RESET_REQUESTED),
            topic_name(ProcessingEvent.IDENTITY_USER_REGISTERED),
        ]

        # Create idempotent message processor
        config = IdempotencyConfig(
            service_name="identity-service-orchestrator",
            default_ttl=86400,  # 24 hours
            enable_debug_logging=True,
        )

        # Processor for identity events
        @idempotent_consumer(redis_client=redis_client, config=config)
        async def process_identity_event_idempotently(
            msg: Any, *, confirm_idempotency: Callable[[], Awaitable[None]]
        ) -> bool | None:
            result = await self._process_message(msg)
            await confirm_idempotency()  # Confirm after successful processing
            return result

        self._process_identity_event_idempotently = process_identity_event_idempotently

    async def start_consumer(self) -> None:
        """Start the Kafka consumer for internal event processing."""
        logger.info("Starting identity service internal Kafka consumer")

        # Create Kafka consumer
        self.consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id="identity_service_internal_consumer",
            auto_offset_reset="latest",
            enable_auto_commit=False,
            max_poll_records=1,  # Process one at a time for consistency
            session_timeout_ms=45000,
        )

        try:
            await self.consumer.start()
            logger.info(
                "Identity service internal Kafka consumer started",
                extra={
                    "topics": self.topics,
                    "group_id": "identity_service_internal_consumer",
                },
            )

            # Start message processing loop
            await self._process_messages()

        except asyncio.CancelledError:
            logger.info("Identity Kafka consumer task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in Identity service Kafka consumer: {e}", exc_info=True)
            raise
        finally:
            await self.stop_consumer()

    async def stop_consumer(self) -> None:
        """Stop the Kafka consumer gracefully."""
        self.should_stop = True
        if self.consumer:
            try:
                await self.consumer.stop()
                logger.info("Identity service Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping Identity service Kafka consumer: {e}")
            finally:
                self.consumer = None

    async def _process_messages(self) -> None:
        """Main message processing loop."""
        if not self.consumer:
            return

        logger.info("Starting Identity service message processing loop")

        while not self.should_stop:
            try:
                async for msg in self.consumer:
                    if self.should_stop:
                        break

                    try:
                        result = await self._process_identity_event_idempotently(msg)

                        if result is not None:
                            # Only commit if not a skipped duplicate
                            if result:
                                await self.consumer.commit()
                                logger.debug(
                                    "Identity event committed: %s:%s:%s",
                                    msg.topic,
                                    msg.partition,
                                    msg.offset,
                                )
                            else:
                                logger.warning(
                                    f"Identity event processing failed, not committing: "
                                    f"{msg.topic}:{msg.partition}:{msg.offset}",
                                )
                        else:
                            # Message was a duplicate and skipped
                            logger.info(
                                f"Duplicate identity event skipped: "
                                f"{msg.topic}:{msg.partition}:{msg.offset}",
                            )

                    except Exception as e:
                        logger.error(f"Error processing identity event: {e}", exc_info=True)

            except KafkaConnectionError as kce:
                logger.error(f"Kafka connection error: {kce}", exc_info=True)
                if self.should_stop:
                    break
                await asyncio.sleep(5)  # Wait before retry
            except asyncio.CancelledError:
                logger.info("Identity message consumption cancelled")
                break
            except Exception as e:
                logger.error(f"Error in identity message processing loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying

        logger.info("Identity service message processing loop has finished")

    async def _process_message(self, msg: Any) -> bool:
        """Process individual Kafka message from Identity Service events.

        Args:
            msg: Kafka consumer record to process

        Returns:
            True if processing succeeded, False otherwise
        """
        logger.debug(f"Processing identity event from {msg.topic}:{msg.partition}:{msg.offset}")

        try:
            # Determine event type by topic and process accordingly
            if msg.topic == topic_name(ProcessingEvent.IDENTITY_EMAIL_VERIFICATION_REQUESTED):
                verification_envelope = EventEnvelope[
                    EmailVerificationRequestedV1
                ].model_validate_json(msg.value)
                verification_event = EmailVerificationRequestedV1.model_validate(
                    verification_envelope.data
                )
                await self.notification_orchestrator.handle_email_verification_requested(
                    verification_event
                )

            elif msg.topic == topic_name(ProcessingEvent.IDENTITY_PASSWORD_RESET_REQUESTED):
                reset_envelope = EventEnvelope[PasswordResetRequestedV1].model_validate_json(
                    msg.value
                )
                reset_event = PasswordResetRequestedV1.model_validate(reset_envelope.data)
                await self.notification_orchestrator.handle_password_reset_requested(reset_event)

            elif msg.topic == topic_name(ProcessingEvent.IDENTITY_USER_REGISTERED):
                registration_envelope = EventEnvelope[UserRegisteredV1].model_validate_json(
                    msg.value
                )
                registration_event = UserRegisteredV1.model_validate(registration_envelope.data)
                await self.notification_orchestrator.handle_user_registered(registration_event)

            else:
                logger.warning(f"Unknown identity event topic: {msg.topic}")
                return False

            logger.info(f"Successfully processed identity event from topic: {msg.topic}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to process identity event from {msg.topic}: {e}",
                exc_info=True,
            )
            return False
