"""
E2E Test Fixtures for Development Stack.

This module provides fixtures that connect directly to running development services.
This approach is:
- Faster: No container startup/teardown
- Simpler: Direct localhost connections
- More realistic: Tests actual running services
- Development-friendly: Works with existing workflow
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp
import pytest_asyncio
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from common_core.event_enums import ProcessingEvent, topic_name

# Service endpoints for running development stack
DEVELOPMENT_SERVICES = {
    "essay_lifecycle_api": "http://localhost:6001",
    "batch_orchestrator": "http://localhost:5001",
    "class_management": "http://localhost:5002",
    "file_service": "http://localhost:7001",
    "batch_conductor": "http://localhost:4002",
    "result_aggregator": "http://localhost:4003",
    "llm_provider": "http://localhost:8090",
    "websocket": "http://localhost:8081",
    "spellchecker": "http://localhost:8002",
    "cj_assessment": "http://localhost:9095",
    "api_gateway": "http://localhost:8080",
}

# Infrastructure endpoints
KAFKA_BOOTSTRAP_SERVERS = "localhost:9093"  # Use external listener port
REDIS_URL = "redis://localhost:6379"


@pytest_asyncio.fixture
async def kafka_producer() -> AsyncGenerator[AIOKafkaProducer, None]:
    """Kafka producer connected to running development Kafka."""
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
    )

    await producer.start()
    try:
        yield producer
    finally:
        await producer.stop()


@pytest_asyncio.fixture
async def kafka_consumer_factory():
    """Factory for creating Kafka consumers for different topics."""
    consumers = []

    def create_consumer(topics: list[str], group_id: str) -> AIOKafkaConsumer:
        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id=group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
            auto_offset_reset="latest",  # Only consume new messages
            enable_auto_commit=True,
        )
        consumers.append(consumer)
        return consumer

    yield create_consumer

    # Cleanup
    for consumer in consumers:
        if not consumer._closed:
            await consumer.stop()


@pytest_asyncio.fixture
async def topic_names() -> dict[str, str]:
    """Map of event names to actual Kafka topic names."""
    return {
        "batch_nlp_initiate_command": topic_name(ProcessingEvent.BATCH_NLP_INITIATE_COMMAND),
        "batch_nlp_processing_requested": topic_name(
            ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED
        ),
        "batch_nlp_analysis_completed": topic_name(ProcessingEvent.BATCH_NLP_ANALYSIS_COMPLETED),
        "essay_nlp_completed": topic_name(ProcessingEvent.ESSAY_NLP_COMPLETED),
    }


class DevelopmentServiceHealthChecker:
    """Health checker for running development services."""

    def __init__(self):
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def is_service_healthy(self, service_name: str) -> bool:
        """Check if a service is healthy via HTTP health endpoint."""
        if service_name not in DEVELOPMENT_SERVICES:
            return False

        url = f"{DEVELOPMENT_SERVICES[service_name]}/healthz"

        try:
            if not self.session:
                return False
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, dict):
                        return bool(data.get("status") == "healthy")
                    return False
                return False
        except Exception:
            return False

    async def wait_for_services_ready(
        self, service_names: list[str], timeout: int = 60
    ) -> dict[str, bool]:
        """Wait for multiple services to be ready."""
        import asyncio

        start_time = asyncio.get_event_loop().time()
        results = {}

        while asyncio.get_event_loop().time() - start_time < timeout:
            for service_name in service_names:
                if service_name not in results:
                    if await self.is_service_healthy(service_name):
                        results[service_name] = True
                        print(f"✅ {service_name} is healthy")

            if len(results) == len(service_names):
                break

            await asyncio.sleep(2)

        # Mark any remaining services as failed
        for service_name in service_names:
            if service_name not in results:
                results[service_name] = False
                print(f"❌ {service_name} failed to become healthy")

        return results


@pytest_asyncio.fixture
async def service_health_checker():
    """Service health checker for development services."""
    async with DevelopmentServiceHealthChecker() as checker:
        yield checker


async def send_event_to_topic(
    producer: AIOKafkaProducer, topic: str, event: Any, key: str | None = None
) -> None:
    """Send an event to a Kafka topic and wait for delivery."""
    # Convert EventEnvelope to dict if needed
    if hasattr(event, "model_dump"):
        event_data = event.model_dump(mode="json")  # Use JSON mode for UUID serialization
    elif hasattr(event, "dict"):
        event_data = event.dict()
    else:
        event_data = event

    await producer.send_and_wait(topic=topic, value=event_data, key=key)
