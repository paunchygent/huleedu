"""
Shared utilities for walking skeleton end-to-end tests.

This module contains common imports, configuration, and the EventCollector class
used across the walking skeleton test suite for maintaining the modular 400-line limit.
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

from aiokafka import AIOKafkaConsumer
from huleedu_service_libs.logging_utils import create_service_logger

# Configure logging for debugging
logger = create_service_logger("test.walking_skeleton_e2e_v2")

# Test Configuration
CONFIG: Dict[str, Any] = {
    "bos_url": "http://localhost:5001",
    "file_service_url": "http://localhost:7001",
    "els_url": "http://localhost:6001",
    "kafka_bootstrap_servers": "localhost:9093",
    "test_timeout": 120,  # 2 minutes total timeout
    "event_wait_timeout": 30,  # 30 seconds for individual events
}

# Event Topics (Architecture Fix)
TOPICS: Dict[str, str] = {
    "batch_registered": "huleedu.batch.essays.registered.v1",
    "content_provisioned": "huleedu.file.essay.content.provisioned.v1",  # NEW
    "batch_ready": "huleedu.els.batch.essays.ready.v1",
    "spellcheck_command": "huleedu.els.spellcheck.initiate.command.v1",
    "spellcheck_requested": "huleedu.essay.spellcheck.requested.v1",
    "excess_content": "huleedu.els.excess.content.provisioned.v1",  # NEW
}


class EventCollector:
    """Collects and manages Kafka events for validation."""

    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self.events: Dict[str, List[Dict[str, Any]]] = {}
        self.running = False

    async def start_collecting(self, topics: List[str], timeout: int = 30):
        """Start collecting events from specified topics."""
        self.running = True
        self.events = {topic: [] for topic in topics}

        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.bootstrap_servers,
            auto_offset_reset="earliest",
            group_id=f"e2e_test_{uuid.uuid4().hex[:8]}",
            value_deserializer=lambda x: json.loads(x.decode("utf-8")),
        )

        try:
            await consumer.start()
            logger.info(f"Started collecting events from topics: {topics}")

            end_time = datetime.now() + timedelta(seconds=timeout)

            async for msg in consumer:
                if not self.running or datetime.now() > end_time:
                    break

                topic = msg.topic
                event_data = msg.value

                self.events[topic].append(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "topic": topic,
                        "data": event_data,
                        "key": msg.key.decode("utf-8") if msg.key else None,
                    }
                )

                logger.info(f"Collected event from {topic}: {json.dumps(event_data, indent=2)}")

        except Exception as e:
            logger.error(f"Error collecting events: {e}")
        finally:
            await consumer.stop()

    def stop_collecting(self):
        """Stop collecting events."""
        self.running = False

    def get_events_for_batch(self, topic: str, batch_id: str) -> List[Dict[str, Any]]:
        """Get all events for a specific batch from a topic."""
        if topic not in self.events:
            return []

        batch_events = []
        for event in self.events[topic]:
            event_data = event["data"]

            # Check if event contains our batch_id
            if isinstance(event_data, dict):
                if "data" in event_data and isinstance(event_data["data"], dict):
                    # EventEnvelope format - check multiple possible locations
                    inner_data = event_data["data"]

                    # Direct batch_id field
                    if inner_data.get("batch_id") == batch_id:
                        batch_events.append(event)
                    # batch_id in entity_ref.entity_id (for command events)
                    elif "entity_ref" in inner_data and isinstance(inner_data["entity_ref"], dict):
                        if inner_data["entity_ref"].get("entity_id") == batch_id:
                            batch_events.append(event)
                    # batch_id in ready_essays for BatchEssaysReady
                    elif "ready_essays" in inner_data:
                        ready_essays = inner_data.get("ready_essays", [])
                        if any(
                            essay.get("batch_id") == batch_id
                            for essay in ready_essays
                            if isinstance(essay, dict)
                        ):
                            batch_events.append(event)

                elif event_data.get("batch_id") == batch_id:
                    # Direct event format
                    batch_events.append(event)
                # batch_id in entity_ref.entity_id (direct format)
                elif "entity_ref" in event_data and isinstance(event_data["entity_ref"], dict):
                    if event_data["entity_ref"].get("entity_id") == batch_id:
                        batch_events.append(event)

        return batch_events

    def get_events_for_correlation(self, topic: str, correlation_id: str) -> List[Dict[str, Any]]:
        """Get all events for a specific correlation ID from a topic."""
        if topic not in self.events:
            return []

        correlation_events = []
        for event in self.events[topic]:
            event_data = event["data"]

            # Check if event contains our correlation_id
            if isinstance(event_data, dict):
                if (
                    "correlation_id" in event_data
                    and event_data["correlation_id"] == correlation_id
                ):
                    correlation_events.append(event)
                elif "data" in event_data and isinstance(event_data["data"], dict):
                    if event_data["data"].get("correlation_id") == correlation_id:
                        correlation_events.append(event)

        return correlation_events
