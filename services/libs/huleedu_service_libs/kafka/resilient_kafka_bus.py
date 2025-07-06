"""
Resilient Kafka Publisher with circuit breaker protection and fallback queue.

This module provides a composition-based wrapper that adds circuit breaker protection
and local message queuing for failed publishes, ensuring zero message loss
during Kafka outages.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, TypeVar

from aiokafka.errors import KafkaError
from huleedu_service_libs.kafka.fallback_handler import FallbackMessageHandler, QueuedMessage
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerError
from pydantic import BaseModel

from common_core import CircuitBreakerState
from common_core.events.envelope import EventEnvelope

logger = create_service_logger("resilient_kafka")

T_EventPayload = TypeVar("T_EventPayload", bound=BaseModel)


class ResilientKafkaPublisher:
    """
    Resilient Kafka publisher using composition to wrap KafkaBus with circuit breaker protection.

    Features:
    - Circuit breaker protection for Kafka publishing
    - Local fallback queue for failed messages
    - Automatic retry when circuit recovers
    - Zero message loss during outages
    - Protocol-compliant with KafkaBus interface
    """

    def __init__(
        self,
        delegate: KafkaBus,
        circuit_breaker: Optional[CircuitBreaker] = None,
        fallback_handler: Optional[FallbackMessageHandler] = None,
        retry_interval: int = 30,
    ):
        """
        Initialize resilient Kafka publisher using composition.

        Args:
            delegate: The actual KafkaBus instance to wrap
            circuit_breaker: Circuit breaker for protection (optional)
            fallback_handler: Custom fallback handler (optional, creates default if None)
            retry_interval: Seconds between retry attempts
        """
        self.delegate = delegate
        self.circuit_breaker = circuit_breaker
        self.retry_interval = retry_interval

        # Use provided fallback handler or create default
        self.fallback_handler = fallback_handler or FallbackMessageHandler(
            max_queue_size=1000,
            retry_interval=retry_interval,
        )

        # Background task for processing fallback queue
        self._recovery_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the delegate Kafka bus and recovery task."""
        await self.delegate.start()

        # Start fallback handler recovery task if circuit breaker is enabled
        if self.circuit_breaker and not self._recovery_task:
            self._recovery_task = asyncio.create_task(self._recovery_loop())
            logger.info(
                f"Started recovery task for resilient Kafka publisher '{self.delegate.client_id}'"
            )

    async def stop(self) -> None:
        """Stop the delegate Kafka bus and cleanup tasks."""
        # Signal shutdown to recovery task
        self._shutdown_event.set()

        # Wait for recovery task to complete
        if self._recovery_task and not self._recovery_task.done():
            try:
                await asyncio.wait_for(self._recovery_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Recovery task did not complete within timeout, cancelling")
                self._recovery_task.cancel()
                try:
                    await self._recovery_task
                except asyncio.CancelledError:
                    pass

        await self.delegate.stop()
        logger.info(f"Stopped resilient Kafka publisher '{self.delegate.client_id}'")

    async def publish(
        self,
        topic: str,
        envelope: EventEnvelope[T_EventPayload],
        key: str | None = None,
    ) -> None:
        """
        Publish message with circuit breaker protection.

        Args:
            topic: Kafka topic to publish to
            envelope: Event envelope to publish
            key: Optional message key

        Raises:
            CircuitBreakerError: If circuit is open and no fallback is available
            Exception: If publish fails and fallback queue is full
        """
        if not self.circuit_breaker:
            # No circuit breaker, delegate directly to wrapped KafkaBus
            return await self.delegate.publish(topic, envelope, key)

        try:
            # Attempt to publish through circuit breaker
            await self.circuit_breaker.call(self.delegate.publish, topic, envelope, key)
            logger.debug(f"Published message to topic '{topic}' via circuit breaker")

        except CircuitBreakerError:
            # Circuit is open, queue message for later retry
            logger.warning(
                f"Circuit breaker is open for Kafka publisher '{self.delegate.client_id}', "
                f"queuing message for topic '{topic}'"
            )
            await self._queue_message_for_retry(topic, envelope, key)

        except (KafkaError, Exception) as e:
            # Kafka error occurred, let circuit breaker handle it
            logger.error(
                f"Kafka publish failed for topic '{topic}': {e}. Queuing message for retry."
            )
            await self._queue_message_for_retry(topic, envelope, key)
            raise

    async def _queue_message_for_retry(
        self,
        topic: str,
        envelope: EventEnvelope[T_EventPayload],
        key: str | None,
    ) -> None:
        """Queue a failed message for later retry."""
        queued_message = QueuedMessage(
            topic=topic,
            envelope=envelope,
            key=key,
            queued_at=datetime.now(timezone.utc),
            retry_count=0,
        )

        try:
            await self.fallback_handler.queue_message(queued_message)
            logger.info(
                f"Queued message for retry: topic='{topic}', "
                f"event_id={envelope.event_id}, queue_size={self.fallback_handler.queue_size()}"
            )
        except Exception as e:
            logger.error(f"Failed to queue message for retry: {e}")
            raise

    async def _recovery_loop(self) -> None:
        """Background task to process fallback queue when circuit recovers."""
        logger.info("Starting Kafka recovery loop")

        while not self._shutdown_event.is_set():
            try:
                # Wait for retry interval or shutdown signal
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=self.retry_interval)
                # If we get here, shutdown was signaled
                break

            except asyncio.TimeoutError:
                # Timeout is expected, continue with recovery attempt
                pass

            # Check if circuit is available and process queued messages
            if (
                self.circuit_breaker
                and self.circuit_breaker.state
                in [CircuitBreakerState.CLOSED, CircuitBreakerState.HALF_OPEN]
                and self.fallback_handler.has_queued_messages()
            ):
                await self._process_queued_messages()

        logger.info("Kafka recovery loop stopped")

    async def _process_queued_messages(self) -> None:
        """Process messages from the fallback queue."""
        processed_count = 0
        failed_count = 0

        logger.info(
            f"Processing {self.fallback_handler.queue_size()} queued messages "
            f"for Kafka bus '{self.client_id}'"
        )

        while self.fallback_handler.has_queued_messages():
            try:
                message = await self.fallback_handler.get_next_message()
                if not message:
                    break

                # Attempt to publish the queued message using delegate
                await self.delegate.publish(message.topic, message.envelope, message.key)

                processed_count += 1
                logger.debug(
                    f"Successfully published queued message: topic='{message.topic}', "
                    f"event_id={message.envelope.event_id}"
                )

            except (KafkaError, Exception) as e:
                # If publishing fails, re-queue the message (with retry limit)
                if message.retry_count < 5:  # Max 5 retries per message
                    message.retry_count += 1
                    await self.fallback_handler.queue_message(message)
                    logger.warning(
                        f"Re-queued message after failure (attempt {message.retry_count}): {e}"
                    )
                else:
                    logger.error(
                        f"Dropping message after {message.retry_count} failed attempts: "
                        f"topic='{message.topic}', event_id={message.envelope.event_id}"
                    )

                failed_count += 1
                # Stop processing on first failure to avoid cascading failures
                break

        if processed_count > 0 or failed_count > 0:
            logger.info(
                f"Recovery batch complete: processed={processed_count}, "
                f"failed={failed_count}, remaining={self.fallback_handler.queue_size()}"
            )

    def get_fallback_queue_size(self) -> int:
        """Get current size of fallback queue."""
        return self.fallback_handler.queue_size()

    def get_circuit_breaker_state(self) -> dict:
        """Get current circuit breaker state."""
        if not self.circuit_breaker:
            return {"enabled": False}

        state = self.circuit_breaker.get_state()
        state["enabled"] = True
        state["fallback_queue_size"] = self.get_fallback_queue_size()
        return state

    @property
    def client_id(self) -> str:
        """Get client ID from delegate KafkaBus."""
        return self.delegate.client_id

    @property
    def bootstrap_servers(self) -> str:
        """Get bootstrap servers from delegate KafkaBus."""
        return self.delegate.bootstrap_servers
