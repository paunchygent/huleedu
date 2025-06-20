"""
Kafka consumer logic for Spell Checker Service.

Handles spellcheck request message processing using injected dependencies.
Refactored to follow clean architecture with DI pattern.
"""

from __future__ import annotations

import asyncio

import aiohttp
from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.errors import KafkaConnectionError
from huleedu_service_libs.idempotency import idempotent_consumer
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol

from common_core.enums import ProcessingEvent, topic_name
from services.spell_checker_service.event_processor import process_single_message
from services.spell_checker_service.protocols import (
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
        kafka_bus: KafkaBus,
        http_session: aiohttp.ClientSession,
        redis_client: RedisClientProtocol,
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
        self.consumer: AIOKafkaConsumer | None = None
        self.should_stop = False

        # Create idempotent message processor with 24-hour TTL
        @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
        async def process_message_idempotently(msg: object) -> bool | None:
            return await process_single_message(
                msg=msg,
                http_session=self.http_session,
                content_client=self.content_client,
                result_store=self.result_store,
                event_publisher=self.event_publisher,
                spell_logic=self.spell_logic,
                kafka_bus=self.kafka_bus,
                consumer_group_id=self.consumer_group,
            )

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

        except Exception as e:
            logger.error(f"Error starting Spell Checker Kafka consumer: {e}")
            raise
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
                logger.error(f"Error stopping Spell Checker Kafka consumer: {e}")
            finally:
                self.consumer = None

    async def _process_messages(self) -> None:
        """Main message processing loop."""
        if not self.consumer:
            return

        logger.info("Starting Spell Checker message processing loop")

        retry_count = 0
        max_retries = 3

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
                        f"partition {tp.partition}"
                    )
                    for msg_count, msg in enumerate(messages):
                        if self.should_stop:
                            break
                        logger.info(f"Processing message {msg_count + 1}/{len(messages)} from {tp}")

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
                                f"(processing_result: {processing_result})"
                            )
                        elif processing_result is None:  # Duplicate - already processed
                            # Still commit to avoid reprocessing the duplicate
                            tp_instance = TopicPartition(msg.topic, msg.partition)
                            offsets = {tp_instance: msg.offset + 1}
                            await self.consumer.commit(offsets)
                            logger.debug(
                                f"Committed offset {msg.offset + 1} for {tp_instance} "
                                f"(duplicate skipped)"
                            )
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
                    break
                await asyncio.sleep(2**retry_count)  # Exponential backoff

            except Exception as e:
                logger.error(f"Error in Spell Checker message processing loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying the loop section

        logger.info("Spell Checker message processing loop has finished.")
