"""
Thin Kafka wrapper using aiokafka for HuleEdu microservices.
"""

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator, Optional, TypeVar  # Added Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from aiokafka.errors import KafkaConnectionError, KafkaTimeoutError
from pydantic import BaseModel

# Assuming common_core is installed and accessible
from common_core.events.envelope import EventEnvelope

logger = logging.getLogger(__name__)  # Use module-level logger

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

T_EventPayload = TypeVar("T_EventPayload", bound=BaseModel)


class KafkaBus:
    def __init__(
        self, *, client_id: str, bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS
    ):
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id  # Store client_id for logging
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            client_id=self.client_id,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
            enable_idempotence=True,
        )
        self._started = False

    async def start(self) -> None:
        if not self._started:
            try:
                await self.producer.start()
                self._started = True
                logger.info(f"KafkaProducer '{self.client_id}' started successfully.")
            except KafkaConnectionError as e:
                logger.error(f"KafkaProducer '{self.client_id}' failed to start: {e}")
                raise

    async def stop(self) -> None:
        if self._started:
            try:
                await self.producer.stop()
                self._started = False
                logger.info(f"KafkaProducer '{self.client_id}' stopped.")
            except Exception as e:
                logger.error(
                    f"Error stopping KafkaProducer '{self.client_id}': {e}",
                    exc_info=True,
                )

    async def publish(
        self,
        topic: str,
        envelope: EventEnvelope[T_EventPayload],
        key: Optional[str] = None,
    ) -> None:
        if not self._started:
            logger.warning(
                f"KafkaProducer '{self.client_id}' not started. Attempting to start."
            )
            await self.start()
            if not self._started:
                logger.error(
                    f"Cannot publish on topic '{topic}', producer '{self.client_id}' is not running."
                )
                raise RuntimeError(f"KafkaProducer '{self.client_id}' is not running.")
        try:
            key_bytes = key.encode("utf-8") if key else None
            future = await self.producer.send_and_wait(
                topic, value=envelope.model_dump(mode="json"), key=key_bytes
            )
            record_metadata = future
            logger.debug(
                f"Message published by '{self.client_id}' to {topic} [partition:{record_metadata.partition}, offset:{record_metadata.offset}] key='{key}' event_id='{envelope.event_id}'"
            )
        except KafkaTimeoutError:
            logger.error(
                f"Timeout publishing message by '{self.client_id}' to topic '{topic}'."
            )
            raise
        except Exception as e:
            logger.error(
                f"Error publishing message by '{self.client_id}' to topic '{topic}': {e}",
                exc_info=True,
            )
            raise


async def consume_events(
    topics: list[str] | str,  # Allow single topic or list of topics
    group_id: str,
    client_id: str,  # For consumer logging
    bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
    auto_offset_reset: str = "earliest",
    enable_auto_commit: bool = False,
    # Add consumer_timeout_ms for non-blocking iteration if needed, e.g. 1000
) -> AsyncIterator[Any]:  # Yields the full AIOKafkaConsumer message object
    consumer = AIOKafkaConsumer(
        topics,
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        client_id=client_id,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        auto_offset_reset=auto_offset_reset,
        enable_auto_commit=enable_auto_commit,
        metadata_max_age_ms=90000,  # How often to refresh metadata
        session_timeout_ms=30000,  # Increased session timeout
        heartbeat_interval_ms=10000,  # Adjusted heartbeat
    )

    # Track running state locally instead of using private attributes
    consumer_running = False

    await consumer.start()
    consumer_running = True
    logger.info(
        f"KafkaConsumer '{client_id}' started for topic(s) '{topics}', group '{group_id}'."
    )
    try:
        async for msg in consumer:  # msg is an AIOKafkaConsumer message object
            logger.debug(
                f"'{client_id}' consumed message from {msg.topic} [partition:{msg.partition}, offset:{msg.offset}] key='{msg.key}'"
            )
            yield msg
            # Manual commit should be handled by the caller after processing
    except KafkaConnectionError as e:
        logger.error(
            f"KafkaConsumer '{client_id}' connection error: {e}", exc_info=True
        )
    except Exception as e:  # Catch any other exception during consumption loop
        logger.error(
            f"KafkaConsumer '{client_id}' unexpected error in consumption loop: {e}",
            exc_info=True,
        )
    finally:
        logger.info(f"KafkaConsumer '{client_id}' stopping...")
        if consumer_running:
            await consumer.stop()
            consumer_running = False
        logger.info(f"KafkaConsumer '{client_id}' stopped.")
