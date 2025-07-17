"""
Thin Kafka wrapper using aiokafka for HuleEdu microservices.
"""

from __future__ import annotations

import json
import os
from typing import TypeVar  # Added Optional

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError, KafkaTimeoutError

# Assuming common_core is installed and accessible
from common_core.events.envelope import EventEnvelope
from pydantic import BaseModel

from .logging_utils import create_service_logger

logger = create_service_logger("kafka-client")  # Use structured logger

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

T_EventPayload = TypeVar("T_EventPayload", bound=BaseModel)


class KafkaBus:
    def __init__(self, *, client_id: str, bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS):
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
        try:
            # Always stop the producer if it exists, regardless of _started state
            # This prevents resource leaks when KafkaBus is created but never started
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
        key: str | None = None,
    ) -> None:
        if not self._started:
            logger.warning(f"KafkaProducer '{self.client_id}' not started. Attempting to start.")
            await self.start()
            if not self._started:
                logger.error(
                    f"Cannot publish on topic '{topic}', "
                    f"producer '{self.client_id}' is not running.",
                )
                raise RuntimeError(f"KafkaProducer '{self.client_id}' is not running.")
        try:
            key_bytes = key.encode("utf-8") if key else None
            future = await self.producer.send_and_wait(
                topic,
                value=envelope.model_dump(mode="json"),
                key=key_bytes,
            )
            record_metadata = future
            logger.debug(
                f"Message published by '{self.client_id}' to {topic} "
                f"[partition:{record_metadata.partition}, offset:{record_metadata.offset}] "
                f"key='{key}' event_id='{envelope.event_id}'",
            )
        except KafkaTimeoutError:
            logger.error(f"Timeout publishing message by '{self.client_id}' to topic '{topic}'.")
            raise
        except Exception as e:
            logger.error(
                f"Error publishing message by '{self.client_id}' to topic '{topic}': {e}",
                exc_info=True,
            )
            raise
