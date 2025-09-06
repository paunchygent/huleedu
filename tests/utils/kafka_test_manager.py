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


class KafkaConsumerPool:
    """Simplified consumer cache - lazy creation with topic-based reuse."""

    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        # Cache: topics_key -> (consumer, loop)
        self._consumer_cache: dict[str, tuple[AIOKafkaConsumer, asyncio.AbstractEventLoop]] = {}
        self._lock = asyncio.Lock()

    async def get_consumer(self, test_name: str, topics: list[str]) -> AIOKafkaConsumer:
        """Get or create consumer for specific topics."""
        topics_key = "|".join(sorted(topics))  # Simple cache key
        current_loop = asyncio.get_event_loop()

        async with self._lock:
            # Check if we have a consumer for these exact topics
            if topics_key in self._consumer_cache:
                consumer, created_loop = self._consumer_cache[topics_key]

                # Verify consumer was created in the same loop
                if created_loop is current_loop:
                    try:
                        # Reset consumer to end positions for clean test isolation
                        await consumer.seek_to_end()
                        logger.info(f"♻️ Reusing cached consumer for {test_name}")
                        return consumer
                    except Exception as e:
                        # Consumer is broken, remove from cache and create new one
                        logger.warning(f"Cached consumer broken for {test_name}, creating new: {e}")
                        try:
                            await consumer.stop()
                        except Exception:
                            # If stop fails, mark as closed to prevent warnings
                            try:
                                consumer._closed = True
                            except Exception:
                                pass
                        del self._consumer_cache[topics_key]
                else:
                    # Consumer from different loop, cannot reuse
                    logger.debug(f"Consumer for {topics_key} from different loop, creating new")
                    # Mark consumer as closed to prevent "Unclosed" warnings
                    try:
                        consumer._closed = True
                    except Exception:
                        pass
                    del self._consumer_cache[topics_key]

            # Create new consumer on-demand
            consumer = AIOKafkaConsumer(
                *topics,  # Subscribe to topics
                bootstrap_servers=self.bootstrap_servers,
                group_id=f"test_{test_name}_{uuid.uuid4().hex[:8]}",
                auto_offset_reset="latest",
                enable_auto_commit=False,
            )

            try:
                await consumer.start()
                # Wait for assignment (sequential creation avoids coordinator overload)
                await self._wait_for_assignment(consumer, test_name)
                await consumer.seek_to_end()

                # Cache it for reuse with loop reference
                self._consumer_cache[topics_key] = (consumer, current_loop)
                logger.info(f"✅ Created and cached consumer for {test_name}")
                return consumer
            except Exception as e:
                # Clean up failed consumer
                try:
                    await consumer.stop()
                except Exception:
                    pass
                raise RuntimeError(f"Failed to create consumer for {test_name}: {e}")

    async def _wait_for_assignment(self, consumer: AIOKafkaConsumer, test_name: str) -> None:
        """Wait for consumer to get partition assignment."""
        start_time = asyncio.get_event_loop().time()

        while True:
            if asyncio.get_event_loop().time() - start_time > 15.0:
                raise RuntimeError(f"Consumer {test_name} partition assignment timeout (15s)")

            assigned_partitions = consumer.assignment()
            if assigned_partitions:
                logger.debug(f"Consumer {test_name} assigned {len(assigned_partitions)} partitions")
                break
            else:
                await asyncio.sleep(0.1)

    async def cleanup_pool(self) -> None:
        """Clean up cached consumers - gracefully handles cross-loop scenarios."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop - just clear cache
            self._consumer_cache.clear()
            logger.info("🧹 Kafka consumer cache cleared (no active loop)")
            return

        # Clean up consumers belonging to current loop, skip others
        async with self._lock:
            consumers_to_remove = []
            same_loop_count = 0
            different_loop_count = 0

            for topics_key, (consumer, created_loop) in list(self._consumer_cache.items()):
                if created_loop is current_loop:
                    # Same loop - safe to stop normally
                    same_loop_count += 1
                    try:
                        await consumer.stop()
                        logger.debug(f"Stopped consumer for topics: {topics_key}")
                    except Exception as e:
                        logger.debug(f"Error stopping consumer {topics_key}: {e}")
                    consumers_to_remove.append(topics_key)
                else:
                    # Different loop - mark as closed and remove from cache
                    different_loop_count += 1
                    try:
                        # Mark consumer as closed to prevent warnings
                        consumer._closed = True
                        logger.debug(f"Removing consumer {topics_key} from cache (different loop)")
                    except Exception as e:
                        logger.debug(f"Error marking consumer {topics_key} as closed: {e}")
                    consumers_to_remove.append(topics_key)

            # Remove all consumers from cache
            for topics_key in consumers_to_remove:
                del self._consumer_cache[topics_key]

        logger.info(
            f"🧹 Kafka consumer cache cleaned up "
            f"({same_loop_count} stopped, {different_loop_count} removed)"
        )


# Global consumer pool instance
_kafka_consumer_pool: KafkaConsumerPool | None = None


def get_or_create_consumer_pool(bootstrap_servers: str) -> KafkaConsumerPool:
    """Get or create the global consumer pool."""
    global _kafka_consumer_pool

    if _kafka_consumer_pool is None:
        _kafka_consumer_pool = KafkaConsumerPool(bootstrap_servers)

    return _kafka_consumer_pool


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
            "els_batch_phase_outcome": "huleedu.els.batch.phase.outcome.v1",
            "pipeline_progress": "huleedu.batch.pipeline.progress.updated.v1",
            "phase_skipped": "huleedu.batch.phase.skipped.v1",  # BCS phase pruning events
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
        self._use_consumer_pool = True  # Enable consumer pooling with simplified implementation

    @asynccontextmanager
    async def consumer(
        self,
        test_name: str,
        topics: list[str] | None = None,
        auto_offset_reset: str = "latest",
    ) -> AsyncIterator[AIOKafkaConsumer]:
        """
        Context manager for Kafka consumer with automatic cleanup and pooling.

        Uses consumer pool for significant performance improvement by reusing consumers
        instead of creating new ones for each test.

        Args:
            test_name: Name of test for unique group ID
            topics: List of topics to subscribe to (uses default if None)
            auto_offset_reset: Offset reset strategy (only "latest" supported with pool)

        Yields:
            Configured and started AIOKafkaConsumer
        """
        if topics is None:
            topics = list(self.config.topics.values())

        if self._use_consumer_pool and auto_offset_reset == "latest":
            # Use consumer pool for significant performance improvement
            pool = get_or_create_consumer_pool(self.config.bootstrap_servers)
            consumer = await pool.get_consumer(test_name, topics)

            try:
                yield consumer
            finally:
                # Consumer stays in pool for reuse, no explicit cleanup here
                # Pool tracks loop ownership and handles cleanup appropriately
                pass
        else:
            # Fallback to individual consumer creation
            async with self._create_individual_consumer(
                test_name, topics, auto_offset_reset
            ) as consumer:
                yield consumer

    @asynccontextmanager
    async def _create_individual_consumer(
        self, test_name: str, topics: list[str], auto_offset_reset: str
    ) -> AsyncIterator[AIOKafkaConsumer]:
        """Create an individual consumer (fallback when pool is not suitable)."""
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
        self,
        consumer: AIOKafkaConsumer,
        test_name: str,
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

            for _topic_partition, messages in msg_batch.items():
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
            consumer,
            expected_count,
            timeout_seconds,
            event_filter,
        )
