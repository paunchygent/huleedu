"""
Kafka consumer logic for Spell Checker Service.

Handles spellcheck request message processing using injected dependencies.
Refactored to follow clean architecture with DI pattern.
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
from common_core.error_enums import ErrorCode
from common_core.event_enums import ProcessingEvent, topic_name
from huleedu_service_libs.error_handling import (
    raise_connection_error,
    raise_initialization_failed,
)
from huleedu_service_libs.error_handling.error_detail_factory import (
    create_error_detail_with_context,
)
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import KafkaPublisherProtocol, RedisClientProtocol

from services.spellchecker_service.event_processor import process_single_message
from services.spellchecker_service.protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
    SpellLogicProtocol,
)

logger = create_service_logger("spell_checker.kafka.consumer")


class SpellCheckerKafkaConsumer:
    """Kafka consumer for handling spellcheck request events."""

    def __init__(
        self,
        kafka_bootstrap_servers: str,
        consumer_group: str,
        consumer_client_id: str,
        content_client: ContentClientProtocol,
        result_store: ResultStoreProtocol,
        spell_logic: SpellLogicProtocol,
        event_publisher: SpellcheckEventPublisherProtocol,
        kafka_bus: KafkaPublisherProtocol,
        http_session: aiohttp.ClientSession,
        redis_client: RedisClientProtocol,
        tracer: "Tracer | None" = None,
    ) -> None:
        """Initialize with injected dependencies."""
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.consumer_group = consumer_group
        self.consumer_client_id = consumer_client_id
        self.content_client = content_client
        self.result_store = result_store
        self.spell_logic = spell_logic
        self.event_publisher = event_publisher
        self.kafka_bus = kafka_bus
        self.http_session = http_session
        self.redis_client = redis_client
        self.tracer = tracer
        self.consumer: AIOKafkaConsumer | None = None
        self.should_stop = False

        # Create idempotency configuration for spellchecker service
        idempotency_config = IdempotencyConfig(
            service_name="spell-checker-service",
            enable_debug_logging=True,  # Enable debug logging for monitoring
        )

        # Create idempotent message processor with v2 decorator
        @idempotent_consumer(redis_client=redis_client, config=idempotency_config)
        async def process_message_idempotently(msg: object, *, confirm_idempotency: Callable[[], Awaitable[None]]) -> bool | None:
            result = await process_single_message(
                msg=msg,
                http_session=self.http_session,
                content_client=self.content_client,
                result_store=self.result_store,
                event_publisher=self.event_publisher,
                spell_logic=self.spell_logic,
                kafka_bus=self.kafka_bus,
                tracer=self.tracer,
                consumer_group_id=self.consumer_group,
            )
            await confirm_idempotency()  # Confirm after successful processing
            return result

        self._process_message_idempotently = process_message_idempotently

    async def start_consumer(self) -> None:
        """Start the Kafka consumer and begin processing messages."""
        input_topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)

        self.consumer = AIOKafkaConsumer(
            input_topic,
            bootstrap_servers=self.kafka_bootstrap_servers,
            group_id=self.consumer_group,
            client_id=self.consumer_client_id,
            enable_auto_commit=False,  # Manual commit for reliable message processing
            auto_offset_reset="earliest",
        )

        try:
            await self.consumer.start()
            logger.info(
                "Spell Checker Kafka consumer started",
                extra={
                    "group_id": self.consumer_group,
                    "topic": input_topic,
                },
            )

            # Start message processing loop
            await self._process_messages()

        except asyncio.CancelledError:
            logger.info("Kafka consumer task cancelled")
            raise
        except KafkaConnectionError as kce:
            # Use structured error handling for Kafka connection issues
            logger.error(f"Kafka connection error during consumer startup: {kce}", exc_info=True)
            raise_connection_error(
                service="spellchecker_service",
                operation="start_kafka_consumer",
                target=self.kafka_bootstrap_servers,
                message=f"Failed to connect to Kafka: {str(kce)}",
                correlation_id=uuid4(),
                consumer_group=self.consumer_group,
                topic=input_topic,
            )
        except Exception as e:
            # Use structured error handling for initialization failures
            logger.error(f"Error in Spell Checker Kafka consumer: {e}", exc_info=True)
            raise_initialization_failed(
                service="spellchecker_service",
                operation="start_kafka_consumer",
                component="kafka_consumer",
                message=f"Failed to initialize Kafka consumer: {str(e)}",
                correlation_id=uuid4(),
                consumer_group=self.consumer_group,
                topic=input_topic,
            )
        finally:
            await self.stop_consumer()

    async def stop_consumer(self) -> None:
        """Stop the Kafka consumer gracefully."""
        self.should_stop = True
        if self.consumer:
            try:
                await self.consumer.stop()
                logger.info("Spell Checker Kafka consumer stopped")
            except Exception as e:
                # Use structured error handling for graceful shutdown failures
                logger.error(f"Error stopping Spell Checker Kafka consumer: {e}", exc_info=True)
                # Create structured error but don't raise (we're shutting down)
                error_detail = create_error_detail_with_context(
                    error_code=ErrorCode.CONNECTION_ERROR,
                    message=f"Error during consumer shutdown: {str(e)}",
                    service="spellchecker_service",
                    operation="stop_kafka_consumer",
                    correlation_id=uuid4(),
                    details={"consumer_group": self.consumer_group},
                    capture_stack=False,
                )
                logger.warning(
                    f"Structured error during shutdown: {error_detail.message}",
                    extra={"correlation_id": str(error_detail.correlation_id)},
                )
            finally:
                self.consumer = None

    async def _process_messages(self) -> None:
        """Main message processing loop."""
        if not self.consumer:
            return

        logger.info("Starting Spell Checker message processing loop")

        retry_count = 0
        max_retries = 3

        # Generate correlation_id for this processing session
        session_correlation_id = uuid4()
        logger.info(
            "Starting message processing session",
            extra={
                "correlation_id": str(session_correlation_id),
                "consumer_group": self.consumer_group,
            },
        )

        while not self.should_stop:
            try:
                # Use DI-provided HTTP session instead of creating ad-hoc sessions
                result = await self.consumer.getmany(timeout_ms=1000, max_records=10)
                if not result:
                    await asyncio.sleep(0.1)  # Short sleep if no messages
                    continue

                for tp, messages in result.items():
                    logger.debug(
                        f"Received {len(messages)} messages from {tp.topic} "
                        f"partition {tp.partition}",
                    )
                    for msg_count, msg in enumerate(messages):
                        if self.should_stop:
                            break
                        logger.info(f"Processing message {msg_count + 1}/{len(messages)} from {tp}")

                        try:
                            processing_result = await self._process_message_idempotently(msg)

                            # Handle three states: True (success),
                            # False (business failure), None (duplicate)
                            # Commit offset for all cases to avoid reprocessing
                            if processing_result is not None:  # True or False - processed message
                                # Store offset for this specific message
                                tp_instance = TopicPartition(msg.topic, msg.partition)
                                offsets = {tp_instance: msg.offset + 1}
                                await self.consumer.commit(offsets)
                                logger.debug(
                                    f"Committed offset {msg.offset + 1} for {tp_instance} "
                                    f"(processing_result: {processing_result})",
                                )
                            elif processing_result is None:  # Duplicate - already processed
                                # Still commit to avoid reprocessing the duplicate
                                tp_instance = TopicPartition(msg.topic, msg.partition)
                                offsets = {tp_instance: msg.offset + 1}
                                await self.consumer.commit(offsets)
                                logger.debug(
                                    f"Committed offset {msg.offset + 1} for {tp_instance} "
                                    f"(duplicate skipped)",
                                )
                        except HuleEduError as he:
                            # Structured error from message processing - log and continue
                            logger.error(
                                f"Structured error processing message offset {msg.offset}: "
                                f"{he.error_detail.message}",
                                exc_info=True,
                                extra={"correlation_id": str(he.error_detail.correlation_id)},
                            )
                            # Still commit offset to avoid reprocessing bad messages
                            tp_instance = TopicPartition(msg.topic, msg.partition)
                            offsets = {tp_instance: msg.offset + 1}
                            await self.consumer.commit(offsets)

                        except Exception as msg_e:
                            # Convert unstructured message processing error
                            logger.error(
                                f"Unhandled error processing message offset {msg.offset}: {msg_e}",
                                exc_info=True,
                            )
                            error_detail = create_error_detail_with_context(
                                error_code=ErrorCode.PROCESSING_ERROR,
                                message=f"Message processing error: {str(msg_e)}",
                                service="spellchecker_service",
                                operation="process_single_message",
                                correlation_id=uuid4(),
                                details={
                                    "topic": msg.topic,
                                    "partition": msg.partition,
                                    "offset": msg.offset,
                                },
                                capture_stack=False,
                            )
                            logger.warning(
                                f"Structured message processing error: {error_detail.message}",
                                extra={"correlation_id": str(error_detail.correlation_id)},
                            )
                            # Still commit offset to avoid reprocessing bad messages
                            tp_instance = TopicPartition(msg.topic, msg.partition)
                            offsets = {tp_instance: msg.offset + 1}
                            await self.consumer.commit(offsets)
                    if self.should_stop:
                        break

                retry_count = 0  # Reset retries on successful processing

            except KafkaConnectionError as kce:
                retry_count += 1
                logger.error(
                    f"Kafka connection error during consumption "
                    f"(attempt {retry_count}/{max_retries}): {kce}",
                    exc_info=True,
                )
                if retry_count >= max_retries or self.should_stop:
                    logger.error("Max retries reached or shutdown signaled. Exiting consumer.")
                    # Create structured error for connection failure
                    raise_connection_error(
                        service="spellchecker_service",
                        operation="consume_kafka_messages",
                        target=self.kafka_bootstrap_servers,
                        message=f"Kafka connection failed after {max_retries} retries: {str(kce)}",
                        correlation_id=uuid4(),
                        retry_count=retry_count,
                        max_retries=max_retries,
                    )
                await asyncio.sleep(2**retry_count)  # Exponential backoff

            except HuleEduError:
                # Already structured error - log and continue
                logger.error(
                    "Structured error in Spell Checker message processing loop",
                    exc_info=True,
                )
                await asyncio.sleep(5)

            except Exception as e:
                # Convert unstructured error to structured error
                logger.error(f"Error in Spell Checker message processing loop: {e}", exc_info=True)
                error_detail = create_error_detail_with_context(
                    error_code=ErrorCode.PROCESSING_ERROR,
                    message=f"Message processing loop error: {str(e)}",
                    service="spellchecker_service",
                    operation="process_messages_loop",
                    correlation_id=uuid4(),
                    details={"consumer_group": self.consumer_group},
                    capture_stack=False,
                )
                logger.warning(
                    f"Structured processing loop error: {error_detail.message}",
                    extra={"correlation_id": str(error_detail.correlation_id)},
                )
                await asyncio.sleep(5)  # Wait before retrying the loop section

        logger.info("Spell Checker message processing loop has finished.")
