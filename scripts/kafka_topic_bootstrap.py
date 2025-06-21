#!/usr/bin/env python3
"""Kafka Topic Bootstrap Script

Automatically creates required Kafka topics based on the topic mapping
defined in common_core.enums. Designed to run as a one-shot service
in Docker Compose to ensure topics exist before other services start.

This script follows HuleEdu architectural patterns:
- Uses async/await for all I/O operations
- Leverages existing topic_name() function from common_core
- Implements robust error handling with retries
- Provides comprehensive logging for operational visibility
"""

from __future__ import annotations

import asyncio
import sys

from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import KafkaConnectionError, TopicAlreadyExistsError

from common_core.enums import _TOPIC_MAPPING, topic_name


class KafkaTopicBootstrap:
    """Handles Kafka topic creation with robust error handling and retry logic."""

    def __init__(
        self,
        bootstrap_servers: str,
        max_retries: int = 10,
        retry_delay: float = 2.0,
        default_partitions: int = 3,
        default_replication_factor: int = 1,
    ) -> None:
        """Initialize the Kafka topic bootstrap client.

        Args:
            bootstrap_servers: Kafka bootstrap servers connection string
            max_retries: Maximum number of connection retry attempts
            retry_delay: Initial delay between retries (exponential backoff)
            default_partitions: Default number of partitions for new topics
            default_replication_factor: Default replication factor for new topics
        """
        self.bootstrap_servers = bootstrap_servers
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.default_partitions = default_partitions
        self.default_replication_factor = default_replication_factor
        self.admin_client: AIOKafkaAdminClient | None = None

    async def __aenter__(self) -> KafkaTopicBootstrap:
        """Async context manager entry - establish Kafka admin client connection."""
        await self._connect_with_retry()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - close Kafka admin client connection."""
        if self.admin_client:
            await self.admin_client.close()

    async def _connect_with_retry(self) -> None:
        """Establish connection to Kafka with exponential backoff retry logic."""
        for attempt in range(1, self.max_retries + 1):
            try:
                print(f"Attempting to connect to Kafka (attempt {attempt}/{self.max_retries})...")
                self.admin_client = AIOKafkaAdminClient(
                    bootstrap_servers=self.bootstrap_servers, client_id="huleedu-topic-bootstrap",
                )
                await self.admin_client.start()
                print("✅ Successfully connected to Kafka")
                return
            except KafkaConnectionError as e:
                if attempt == self.max_retries:
                    print(f"❌ Failed to connect to Kafka after {self.max_retries} attempts")
                    raise ConnectionError(
                        f"Could not connect to Kafka at {self.bootstrap_servers} "
                        f"after {self.max_retries} attempts. Last error: {e}",
                    ) from e

                delay = self.retry_delay * (2 ** (attempt - 1))  # Exponential backoff
                print(f"⚠️  Connection failed: {e}. Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)

    def _discover_required_topics(self) -> list[str]:
        """Discover all required topics from the common_core topic mapping.

        Returns:
            List of topic names that need to be created
        """
        topics = []
        for event in _TOPIC_MAPPING:
            try:
                topic = topic_name(event)
                topics.append(topic)
            except ValueError as e:
                print(f"⚠️  Skipping unmapped event {event.name}: {e}")

        print(f"📋 Discovered {len(topics)} topics from common_core mapping:")
        for topic in topics:
            print(f"   - {topic}")

        return topics

    async def _get_existing_topics(self) -> list[str]:
        """Get list of existing topics from Kafka cluster.

        Returns:
            List of existing topic names
        """
        if not self.admin_client:
            raise RuntimeError("Admin client not connected")

        # Use list_topics() to get existing topics - returns a set of topic names
        existing_topics_set = await self.admin_client.list_topics()
        existing_topics = list(existing_topics_set)
        print(f"📊 Found {len(existing_topics)} existing topics in cluster")
        return existing_topics

    async def _create_topic(self, topic_name: str) -> bool:
        """Create a single Kafka topic.

        Args:
            topic_name: Name of the topic to create

        Returns:
            True if topic was created, False if it already existed

        Raises:
            Exception: If topic creation failed for reasons other than already existing
        """
        if not self.admin_client:
            raise RuntimeError("Admin client not connected")

        new_topic = NewTopic(
            name=topic_name,
            num_partitions=self.default_partitions,
            replication_factor=self.default_replication_factor,
        )

        try:
            await self.admin_client.create_topics([new_topic])
            print(f"✅ Created topic: {topic_name}")
            return True
        except TopicAlreadyExistsError:
            print(f"ℹ️  Topic already exists: {topic_name}")
            return False
        except Exception as e:
            print(f"❌ Failed to create topic {topic_name}: {e}")
            raise

    async def bootstrap_topics(self) -> dict[str, bool]:
        """Bootstrap all required Kafka topics.

        Returns:
            Dictionary mapping topic names to creation status (True=created, False=existed)
        """
        required_topics = self._discover_required_topics()
        existing_topics = await self._get_existing_topics()

        results = {}
        topics_to_create = [topic for topic in required_topics if topic not in existing_topics]

        if not topics_to_create:
            print("✅ All required topics already exist")
            return {topic: False for topic in required_topics}

        print(f"🚀 Creating {len(topics_to_create)} new topics...")

        for topic in topics_to_create:
            try:
                created = await self._create_topic(topic)
                results[topic] = created
            except Exception as e:
                print(f"❌ Critical error creating topic {topic}: {e}")
                raise

        # Add existing topics to results
        for topic in required_topics:
            if topic not in results:
                results[topic] = False

        return results


async def main() -> None:
    """Main entry point for the Kafka topic bootstrap script."""
    import os

    # Get configuration from environment variables
    # Use external port 9093 for host connections, internal port 9092 for Docker
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093")
    max_retries = int(os.getenv("KAFKA_CONNECT_MAX_RETRIES", "10"))
    retry_delay = float(os.getenv("KAFKA_CONNECT_RETRY_DELAY", "2.0"))
    default_partitions = int(os.getenv("KAFKA_DEFAULT_PARTITIONS", "3"))
    default_replication_factor = int(os.getenv("KAFKA_DEFAULT_REPLICATION_FACTOR", "1"))

    print("🚀 HuleEdu Kafka Topic Bootstrap")
    print(f"📡 Connecting to: {bootstrap_servers}")
    print(
        f"⚙️  Config: {max_retries} retries, {retry_delay}s delay, "
        f"{default_partitions} partitions, {default_replication_factor} replicas",
    )

    try:
        async with KafkaTopicBootstrap(
            bootstrap_servers=bootstrap_servers,
            max_retries=max_retries,
            retry_delay=retry_delay,
            default_partitions=default_partitions,
            default_replication_factor=default_replication_factor,
        ) as bootstrap:
            results = await bootstrap.bootstrap_topics()

            created_count = sum(1 for created in results.values() if created)
            total_count = len(results)

            print("\n📊 Bootstrap Summary:")
            print(f"   - Total topics: {total_count}")
            print(f"   - Created: {created_count}")
            print(f"   - Already existed: {total_count - created_count}")

            if created_count > 0:
                print(f"\n✅ Successfully created {created_count} new topics")
            else:
                print(f"\n✅ All {total_count} required topics were already present")

            print("🎉 Kafka topic bootstrap completed successfully")

    except Exception as e:
        print(f"\n❌ Kafka topic bootstrap failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
