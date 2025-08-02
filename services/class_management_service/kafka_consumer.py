"""
Kafka consumer logic for Class Management Service.

Handles incoming events for student-essay association validation workflow.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Awaitable, Callable
from uuid import uuid4

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

import aiohttp
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError
from common_core.event_enums import ProcessingEvent, topic_name
from huleedu_service_libs.error_handling import (
    raise_connection_error,
    raise_initialization_failed,
)
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.class_management_service.event_processor import process_single_message
from services.class_management_service.protocols import CommandHandlerProtocol

logger = create_service_logger("class_management_service.kafka.consumer")


class ClassManagementKafkaConsumer:
    """Kafka consumer for handling Class Management Service events."""

    def __init__(
        self,
        kafka_bootstrap_servers: str,
        consumer_group: str,
        consumer_client_id: str,
        redis_client: AtomicRedisClientProtocol,
        command_handlers: dict[str, CommandHandlerProtocol],
        tracer: "Tracer | None" = None,
    ) -> None:
        """Initialize with injected dependencies."""
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.consumer_group = consumer_group
        self.consumer_client_id = consumer_client_id
        self.redis_client = redis_client
        self.command_handlers = command_handlers
        self.tracer = tracer
        self.consumer: AIOKafkaConsumer | None = None
        self.should_stop = False
        self.http_session: aiohttp.ClientSession | None = None

        # Create idempotency configuration for Class Management service
        idempotency_config = IdempotencyConfig(
            service_name="class-management-service",
            enable_debug_logging=True,  # Enable debug logging for monitoring
        )

        # Create idempotent message processor with v2 decorator
        @idempotent_consumer(redis_client=redis_client, config=idempotency_config)
        async def process_message_idempotently(
            msg: object, *, confirm_idempotency: Callable[[], Awaitable[None]]
        ) -> bool | None:
            # Ensure HTTP session exists
            if not self.http_session:
                self.http_session = aiohttp.ClientSession()

            result = await process_single_message(
                msg=msg,
                command_handlers=self.command_handlers,
                http_session=self.http_session,
                tracer=self.tracer,
            )
            await confirm_idempotency()  # Confirm after successful processing
            return result

        self._process_message_idempotently = process_message_idempotently

    async def start_consumer(self) -> None:
        """Start the Kafka consumer and begin processing messages."""
        # Subscribe to Phase 1 student matching results from NLP Service
        batch_matches_topic = topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED)

        self.consumer = AIOKafkaConsumer(
            batch_matches_topic,
            bootstrap_servers=self.kafka_bootstrap_servers,
            group_id=self.consumer_group,
            client_id=self.consumer_client_id,
            enable_auto_commit=False,  # Manual commit for reliable message processing
            auto_offset_reset="earliest",
        )

        try:
            # Create HTTP session for external API calls
            self.http_session = aiohttp.ClientSession()

            await self.consumer.start()
            logger.info(
                "Class Management Kafka consumer started",
                extra={
                    "group_id": self.consumer_group,
                    "topics": [batch_matches_topic],
                },
            )

            # Start message processing loop
            await self._process_messages()

        except asyncio.CancelledError:
            logger.info("Kafka consumer task cancelled")
            raise
        except KafkaConnectionError as kce:
            logger.error(f"Kafka connection error during consumer startup: {kce}", exc_info=True)
            raise_connection_error(
                service="class_management_service",
                operation="start_kafka_consumer",
                target=self.kafka_bootstrap_servers,
                message=f"Failed to connect to Kafka: {str(kce)}",
                correlation_id=uuid4(),
                consumer_group=self.consumer_group,
                topics=[batch_matches_topic],
            )
        except Exception as e:
            logger.error(f"Error in Class Management Kafka consumer: {e}", exc_info=True)
            raise_initialization_failed(
                service="class_management_service",
                operation="start_kafka_consumer",
                component="kafka_consumer",
                message=f"Failed to initialize Kafka consumer: {str(e)}",
                correlation_id=uuid4(),
                consumer_group=self.consumer_group,
                topics=[batch_matches_topic],
            )
        finally:
            await self.stop_consumer()

    async def stop_consumer(self) -> None:
        """Stop the Kafka consumer gracefully."""
        self.should_stop = True

        # Close HTTP session if exists
        if self.http_session:
            try:
                await self.http_session.close()
                logger.info("HTTP session closed")
            except Exception as e:
                logger.error(f"Error closing HTTP session: {e}")
            finally:
                self.http_session = None

        # Stop Kafka consumer
        if self.consumer:
            try:
                await self.consumer.stop()
                logger.info("Class Management Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping Class Management Kafka consumer: {e}")
            finally:
                self.consumer = None

    async def _process_messages(self) -> None:
        """Main message processing loop."""
        if not self.consumer:
            return

        logger.info("Starting Class Management message processing loop")

        try:
            async for msg in self.consumer:
                if self.should_stop:
                    logger.info("Shutdown requested, stopping message processing")
                    break

                try:
                    # Process message with idempotency support
                    result = await self._process_message_idempotently(msg)

                    if result is not None:
                        # Only commit if not a skipped duplicate
                        if result:
                            # Commit offset only after successful processing
                            await self.consumer.commit()
                            logger.debug(
                                "Successfully processed and committed message",
                                extra={
                                    "topic": msg.topic,
                                    "partition": msg.partition,
                                    "offset": msg.offset,
                                },
                            )
                        else:
                            logger.warning(
                                "Failed to process message, not committing offset",
                                extra={
                                    "topic": msg.topic,
                                    "partition": msg.partition,
                                    "offset": msg.offset,
                                },
                            )
                    else:
                        # Message was a duplicate and skipped
                        logger.info(
                            "Duplicate message skipped, committing offset",
                            extra={
                                "topic": msg.topic,
                                "partition": msg.partition,
                                "offset": msg.offset,
                            },
                        )
                        # Commit duplicate messages to advance offset
                        await self.consumer.commit()

                except Exception as e:
                    logger.error(
                        "Error processing message",
                        extra={
                            "error": str(e),
                            "topic": msg.topic,
                            "partition": msg.partition,
                            "offset": msg.offset,
                        },
                        exc_info=True,
                    )
                    # Don't commit on error - message will be reprocessed

        except Exception as e:
            logger.error(f"Error in message processing loop: {e}", exc_info=True)
            raise