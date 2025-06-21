"""
Kafka Test Manager

Explicit utilities for Kafka testing and event collection.
Provides clear resource management without pytest fixture magic.

Based on modern testing practices:
- Explicit consumer lifecycle management
- Clear resource ownership and cleanup
- Support for parallel test execution
- Context managers for resource safety
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, NamedTuple

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("test.kafka_manager")


class KafkaTestConfig(NamedTuple):
    """Kafka testing configuration."""

    bootstrap_servers: str
    topics: dict[str, str]
    assignment_timeout: int


def create_kafka_test_config(
    bootstrap_servers: str = "localhost:9093",
    topics: dict[str, str] | None = None,
    assignment_timeout: int = 15,
) -> KafkaTestConfig:
    """Create KafkaTestConfig with default HuleEdu topics if not provided."""
    if topics is None:
        # Default HuleEdu event topics
        topics = {
            "batch_registered": "huleedu.batch.essays.registered.v1",
            "content_provisioned": "huleedu.file.essay.content.provisioned.v1",
            "validation_failed": "huleedu.file.essay.validation.failed.v1",
            "batch_ready": "huleedu.els.batch.essays.ready.v1",
            "batch_spellcheck_initiate": "huleedu.batch.spellcheck.initiate.command.v1",
            "spellcheck_completed": "huleedu.essay.spellcheck.completed.v1",
            "batch_cj_assessment_initiate": "huleedu.batch.cj_assessment.initiate.command.v1",
            "cj_assessment_completed": "huleedu.cj_assessment.completed.v1",
            "els_batch_phase_outcome": "huleedu.els.batch_phase.outcome.v1",
            "pipeline_progress": "huleedu.batch.pipeline.progress.updated.v1",
        }
    return KafkaTestConfig(bootstrap_servers, topics, assignment_timeout)


class KafkaTestManager:
    """
    Explicit Kafka testing utilities.

    Replaces complex Kafka fixtures with clear resource management.
    """

    def __init__(self, config: KafkaTestConfig | None = None):
        self.config = config or create_kafka_test_config()
        self._created_consumers: list[AIOKafkaConsumer] = []

    @asynccontextmanager
    async def consumer(
        self, test_name: str, topics: list[str] | None = None, auto_offset_reset: str = "latest",
    ) -> AsyncIterator[AIOKafkaConsumer]:
        """
        Context manager for Kafka consumer with automatic cleanup.

        Args:
            test_name: Name of test for unique group ID
            topics: List of topics to subscribe to (uses default if None)
            auto_offset_reset: Offset reset strategy

        Yields:
            Configured and started AIOKafkaConsumer
        """
        if topics is None:
            topics = list(self.config.topics.values())

        consumer_group_id = f"test_{test_name}_{uuid.uuid4().hex[:8]}"

        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.config.bootstrap_servers,
            group_id=consumer_group_id,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=False,
        )

        try:
            await consumer.start()
            self._created_consumers.append(consumer)
            logger.info(f"Consumer started for test: {test_name}")

            # Wait for partition assignment and position consumer
            await self._wait_for_partition_assignment(consumer, test_name)

            if auto_offset_reset == "latest":
                await consumer.seek_to_end()
                logger.info("Consumer positioned at end of all topics")

            yield consumer

        finally:
            try:
                await consumer.stop()
                if consumer in self._created_consumers:
                    self._created_consumers.remove(consumer)
                logger.info(f"Consumer stopped for test: {test_name}")
            except Exception as e:
                logger.warning(f"Error stopping consumer for {test_name}: {e}")

    async def _wait_for_partition_assignment(
        self, consumer: AIOKafkaConsumer, test_name: str,
    ) -> None:
        """Wait for consumer to get partition assignment."""
        partitions_assigned = False
        start_time = asyncio.get_event_loop().time()

        while not partitions_assigned:
            if asyncio.get_event_loop().time() - start_time > self.config.assignment_timeout:
                raise RuntimeError(
                    f"Kafka consumer for {test_name} did not get partition assignment "
                    f"within {self.config.assignment_timeout}s",
                )

            assigned_partitions = consumer.assignment()
            if assigned_partitions:
                logger.info(f"Consumer assigned partitions: {assigned_partitions}")
                partitions_assigned = True
            else:
                await asyncio.sleep(0.2)

    async def collect_events(
        self,
        consumer: AIOKafkaConsumer,
        expected_count: int,
        timeout_seconds: int = 30,
        event_filter: Callable[[dict[str, Any]], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Collect events from Kafka consumer.

        Production services access: msg.value -> EventEnvelope -> envelope.data
        Test utility returns: EventEnvelope with topic metadata for test validation

        ACTUAL STRUCTURE RETURNED:
        - events[0] = {"topic": "topic_name", "data": EventEnvelope}
        - events[0]["data"] = EventEnvelope layer (event_id, event_type, correlation_id, data, etc.)
        - events[0]["data"]["data"] = Actual event payload (e.g., CJAssessmentCompletedV1)

        This provides both EventEnvelope structure and topic metadata for comprehensive
        test validation.

        Args:
            consumer: Active Kafka consumer
            expected_count: Number of events to collect
            timeout_seconds: Maximum time to wait
            event_filter: Optional filter function for events

        Returns:
            List of EventEnvelope data (matching production EventEnvelope structure)
        """
        collected_events: list[dict[str, Any]] = []
        end_time = asyncio.get_event_loop().time() + timeout_seconds

        while len(collected_events) < expected_count and asyncio.get_event_loop().time() < end_time:
            msg_batch = await consumer.getmany(timeout_ms=1000, max_records=10)

            for topic_partition, messages in msg_batch.items():
                for message in messages:
                    # Parse raw message like production services do
                    raw_message = message.value
                    if isinstance(raw_message, bytes):
                        raw_message = raw_message.decode("utf-8")

                    try:
                        # Parse JSON to get EventEnvelope data (like production services)
                        event_data = (
                            json.loads(raw_message) if isinstance(raw_message, str) else raw_message
                        )
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse message from {message.topic}")
                        continue

                    # Apply filter if provided (now works on EventEnvelope data directly)
                    if event_filter and not event_filter(event_data):
                        continue

                    # Return EventEnvelope data with topic metadata for test utilities
                    enriched_event = {
                        "topic": message.topic,
                        "data": event_data,  # EventEnvelope structure
                    }
                    collected_events.append(enriched_event)
                    logger.info(
                        f"Collected event from {message.topic}: "
                        f"{event_data.get('event_type', 'unknown')}",
                    )

        return collected_events

    async def cleanup_all_consumers(self) -> None:
        """Clean up all created consumers."""
        for consumer in self._created_consumers.copy():
            try:
                await consumer.stop()
                self._created_consumers.remove(consumer)
            except Exception as e:
                logger.warning(f"Error cleaning up consumer: {e}")

    async def publish_event(self, topic: str, event_data: dict[str, Any]) -> None:
        """
        Publish an event to a Kafka topic.

        Used for test event publishing to simulate service interactions.
        Replaces manual AIOKafkaProducer setup in test files.

        Args:
            topic: Kafka topic name to publish to
            event_data: Event data (EventEnvelope structure)

        Raises:
            RuntimeError: If event publishing fails
        """
        producer = AIOKafkaProducer(
            bootstrap_servers=self.config.bootstrap_servers,
            value_serializer=lambda x: json.dumps(x).encode("utf-8"),
        )

        try:
            await producer.start()
            # Use essay_id as message key if available (matches original implementation)
            message_key = None
            if "data" in event_data and "entity_ref" in event_data["data"]:
                essay_id = event_data["data"]["entity_ref"].get("entity_id")
                if essay_id:
                    message_key = essay_id.encode("utf-8")

            await producer.send_and_wait(topic, event_data, key=message_key)
            logger.info(f"Event published to {topic}: {event_data.get('event_type', 'unknown')}")
        except Exception as e:
            raise RuntimeError(f"Failed to publish event to {topic}: {e}")
        finally:
            await producer.stop()


# Global instance for convenience
kafka_manager = KafkaTestManager()


# Convenience functions for common patterns
@asynccontextmanager
async def kafka_event_monitor(test_name: str, topics: list[str] | None = None):
    """Convenience context manager for event monitoring."""
    async with kafka_manager.consumer(test_name, topics) as consumer:
        yield consumer


async def collect_kafka_events(
    test_name: str,
    expected_count: int,
    timeout_seconds: int = 30,
    topics: list[str] | None = None,
    event_filter: Callable[[dict[str, Any]], bool] | None = None,
) -> list[dict[str, Any]]:
    """
    Convenience function for collecting events.

    Creates consumer, collects events, and cleans up automatically.
    """
    async with kafka_event_monitor(test_name, topics) as consumer:
        return await kafka_manager.collect_events(
            consumer, expected_count, timeout_seconds, event_filter,
        )
