"""
Kafka consumer logic for NLP Service.

Skeleton implementation that handles batch NLP initiate commands.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Awaitable, Callable
from uuid import uuid4

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

import aiohttp
from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.errors import KafkaConnectionError
from common_core.event_enums import ProcessingEvent, topic_name
from huleedu_service_libs.error_handling import (
    raise_connection_error,
    raise_initialization_failed,
)
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.nlp_service.event_processor import process_single_message
from services.nlp_service.protocols import CommandHandlerProtocol

logger = create_service_logger("nlp_service.kafka.consumer")


class NlpKafkaConsumer:
    """Kafka consumer for handling NLP analysis request events."""

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

        # Create idempotency configuration for NLP service
        idempotency_config = IdempotencyConfig(
            service_name="nlp-service",
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
        # Listen for both Phase 1 student matching and Phase 2 NLP commands
        phase1_topic = topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED)
        phase2_topic = topic_name(ProcessingEvent.BATCH_NLP_INITIATE_COMMAND)

        self.consumer = AIOKafkaConsumer(
            phase1_topic,
            phase2_topic,
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
                "NLP Kafka consumer started",
                extra={
                    "group_id": self.consumer_group,
                    "topics": [phase1_topic, phase2_topic],
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
                service="nlp_service",
                operation="start_kafka_consumer",
                target=self.kafka_bootstrap_servers,
                message=f"Failed to connect to Kafka: {str(kce)}",
                correlation_id=uuid4(),
                consumer_group=self.consumer_group,
                topics=[phase1_topic, phase2_topic],
            )
        except Exception as e:
            logger.error(f"Error in NLP Kafka consumer: {e}", exc_info=True)
            raise_initialization_failed(
                service="nlp_service",
                operation="start_kafka_consumer",
                component="kafka_consumer",
                message=f"Failed to initialize Kafka consumer: {str(e)}",
                correlation_id=uuid4(),
                consumer_group=self.consumer_group,
                topics=[phase1_topic, phase2_topic],
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
                logger.debug("HTTP session closed")
            except Exception as e:
                logger.error(f"Error closing HTTP session: {e}", exc_info=True)
            finally:
                self.http_session = None

        if self.consumer:
            try:
                await self.consumer.stop()
                logger.info("NLP Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping NLP Kafka consumer: {e}", exc_info=True)
            finally:
                self.consumer = None

    async def _process_messages(self) -> None:
        """Main message processing loop."""
        if not self.consumer:
            return

        logger.info("Starting NLP message processing loop")

        while not self.should_stop:
            try:
                result = await self.consumer.getmany(timeout_ms=1000, max_records=10)
                if not result:
                    await asyncio.sleep(0.1)  # Short sleep if no messages
                    continue

                for tp, messages in result.items():
                    logger.debug(
                        f"Received {len(messages)} messages from {tp.topic} "
                        f"partition {tp.partition}",
                    )
                    for msg in messages:
                        if self.should_stop:
                            break

                        try:
                            processing_result = await self._process_message_idempotently(msg)

                            # Handle three states: True (success),
                            # False (business failure), None (duplicate)
                            # Commit offset for all cases to avoid reprocessing
                            tp_instance = TopicPartition(msg.topic, msg.partition)
                            offsets = {tp_instance: msg.offset + 1}
                            await self.consumer.commit(offsets)

                            if processing_result is None:
                                logger.debug(f"Duplicate message skipped at offset {msg.offset}")
                            else:
                                logger.debug(
                                    f"Message processed with result: {processing_result} "
                                    f"at offset {msg.offset}"
                                )

                        except Exception as msg_e:
                            logger.error(
                                f"Error processing message offset {msg.offset}: {msg_e}",
                                exc_info=True,
                            )
                            # Still commit offset to avoid reprocessing bad messages
                            tp_instance = TopicPartition(msg.topic, msg.partition)
                            offsets = {tp_instance: msg.offset + 1}
                            await self.consumer.commit(offsets)

            except KafkaConnectionError as kce:
                logger.error(f"Kafka connection error during consumption: {kce}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying

            except Exception as e:
                logger.error(f"Error in NLP message processing loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying

        logger.info("NLP message processing loop has finished.")
