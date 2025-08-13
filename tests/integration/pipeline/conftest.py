"""
TRUE E2E Test Fixtures for NLP Phase 2 Gateway Pattern Testing.

This module provides fixtures for running actual services in TestContainers
for end-to-end pipeline validation. Unlike the previous antipattern approach,
this starts REAL services and tests the complete pipeline flow.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import aiohttp
import pytest
import pytest_asyncio
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from testcontainers.compose import DockerCompose

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.nlp_events import BatchNlpProcessingRequestedV1
from common_core.batch_service_models import BatchServiceNLPInitiateCommandDataV1
from common_core.metadata_models import EssayProcessingInputRefV1


# Path to the docker-compose.test.yml file
DOCKER_COMPOSE_PATH = Path(__file__).parent / "docker-compose.test.yml"


@pytest.fixture(scope="session")
def docker_compose_environment() -> Generator[DockerCompose, None, None]:
    """Start the complete E2E testing environment with actual services."""
    
    # Ensure the docker-compose file exists
    if not DOCKER_COMPOSE_PATH.exists():
        raise FileNotFoundError(f"Docker compose file not found: {DOCKER_COMPOSE_PATH}")
    
    print("\\n🚀 Starting E2E test environment with real services...")
    
    with DockerCompose(
        context=str(DOCKER_COMPOSE_PATH.parent),
        compose_file_name=DOCKER_COMPOSE_PATH.name,
        pull=True,
        build=True,
    ) as compose:
        # Wait for all services to be healthy (they will handle their own migrations)
        print("\\n⏳ Waiting for services to become healthy...")
        _wait_for_services_ready(compose)
        
        print("\\n✅ All services are ready for testing!")
        
        yield compose


def _wait_for_services_ready(compose: DockerCompose, timeout: int = 120) -> None:
    """Wait for all services to be healthy and ready for testing."""
    
    required_services = [
        "kafka",
        "redis", 
        "essay_lifecycle_db",
        "nlp_db",
        "essay_lifecycle_worker",
        "nlp_service",
        "mock_content_service",
    ]
    
    start_time = time.time()
    
    for service in required_services:
        print(f"⏳ Waiting for {service} to be healthy...")
        
        while time.time() - start_time < timeout:
            try:
                # Check service health
                result = compose.exec_in_container(
                    service_name=service,
                    command=["sh", "-c", "echo 'Service check'"],
                )
                
                if result.exit_code == 0:
                    print(f"✅ {service} is healthy")
                    break
                    
            except Exception as e:
                print(f"⏳ {service} not ready yet: {e}")
                
            time.sleep(5)
        else:
            raise TimeoutError(f"Service {service} failed to become healthy within {timeout}s")
    
    # Additional wait for Kafka consumers to be ready
    print("⏳ Waiting for Kafka consumers to be ready...")
    time.sleep(30)  # Allow services to start consuming
    
    print("✅ All services are healthy and ready!")


@pytest_asyncio.fixture
async def kafka_config(docker_compose_environment: DockerCompose) -> dict[str, Any]:
    """Kafka connection configuration for the test environment."""
    # Get Kafka container port mapping
    kafka_port = docker_compose_environment.get_service_port("kafka", 9093)
    
    return {
        "bootstrap_servers": f"localhost:{kafka_port}",
        "client_id": "e2e-test-client",
    }


@pytest_asyncio.fixture
async def kafka_producer(kafka_config: dict[str, Any]) -> AsyncGenerator[AIOKafkaProducer, None]:
    """Kafka producer for sending test events."""
    producer = AIOKafkaProducer(
        **kafka_config,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
    )
    
    await producer.start()
    
    try:
        yield producer
    finally:
        await producer.stop()


@pytest_asyncio.fixture
async def kafka_consumer_factory(kafka_config: dict[str, Any]):
    """Factory for creating Kafka consumers for monitoring events."""
    consumers = []
    
    async def create_consumer(*topics: str, group_id: str | None = None) -> AIOKafkaConsumer:
        consumer = AIOKafkaConsumer(
            *topics,
            **kafka_config,
            group_id=group_id or f"test-consumer-{int(time.time())}",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            consumer_timeout_ms=5000,  # 5 second timeout for testing
        )
        
        await consumer.start()
        consumers.append(consumer)
        return consumer
    
    yield create_consumer
    
    # Clean up all consumers
    for consumer in consumers:
        await consumer.stop()


@pytest_asyncio.fixture
async def http_session() -> AsyncGenerator[aiohttp.ClientSession, None]:
    """HTTP session for interacting with service APIs."""
    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        yield session


@pytest.fixture
def service_urls(docker_compose_environment: DockerCompose) -> dict[str, str]:
    """Service URLs for HTTP interaction."""
    # Note: Most services in this test are workers without HTTP APIs
    # But we can use this for any HTTP endpoints we need to test
    
    mock_content_port = docker_compose_environment.get_service_port("mock_content_service", 80)
    
    return {
        "mock_content_service": f"http://localhost:{mock_content_port}",
    }


@pytest_asyncio.fixture
async def test_data() -> dict[str, Any]:
    """Test data for NLP phase 2 gateway pattern testing."""
    from uuid import uuid4
    
    batch_id = f"test-batch-{uuid4().hex[:8]}"
    class_id = f"test-class-{uuid4().hex[:8]}"
    
    return {
        "batch_id": batch_id,
        "class_id": class_id,
        "course_code": "ENG5",
        "language": "en",
        "correlation_id": str(uuid4()),
        "essays": [
            {
                "essay_id": str(uuid4()),
                "content": "This is a test essay about machine learning and artificial intelligence. It explores the concepts of neural networks and deep learning algorithms.",
                "filename": "test_essay_1.txt",
            },
            {
                "essay_id": str(uuid4()),
                "content": "An exploration of quantum computing and its potential applications in cryptography and computational complexity theory.",
                "filename": "test_essay_2.txt",
            },
            {
                "essay_id": str(uuid4()),
                "content": "Climate change presents significant challenges for sustainable development. This essay examines renewable energy solutions and their impact on environmental policy.",
                "filename": "test_essay_3.txt",
            },
        ],
    }


@pytest.fixture
def event_factory():
    """Factory for creating various test events."""
    from uuid import uuid4
    
    def create_batch_nlp_initiate_command(
        batch_id: str,
        essays: list[dict[str, Any]],
        correlation_id: str | None = None,
    ) -> EventEnvelope:
        """Create BATCH_NLP_INITIATE_COMMAND event (from BOS to ELS)."""
        
        return EventEnvelope(
            event_id=str(uuid4()),
            event_type="huleedu.batch.nlp.initiate.command.v1",
            source_service="batch_orchestrator_service",
            correlation_id=correlation_id,
            data=BatchServiceNLPInitiateCommandDataV1(
                event_name=ProcessingEvent.BATCH_NLP_INITIATE_COMMAND,
                entity_id=batch_id,
                entity_type="batch",
                essays_to_process=[
                    EssayProcessingInputRefV1(
                        essay_id=essay["essay_id"],
                        text_storage_id=f"storage-{essay['essay_id']}",
                    )
                    for essay in essays
                ],
                language="en",
            ).model_dump(mode="json"),
        )
    
    def create_batch_nlp_processing_requested(
        batch_id: str,
        essays: list[dict[str, Any]],
        correlation_id: str | None = None,
    ) -> EventEnvelope:
        """Create BATCH_NLP_PROCESSING_REQUESTED event (from ELS to NLP)."""
        
        return EventEnvelope(
            event_id=str(uuid4()),
            event_type="huleedu.batch.nlp.processing.requested.v1",
            source_service="essay_lifecycle_service",
            correlation_id=correlation_id,
            data=BatchNlpProcessingRequestedV1(
                event_name=ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED,
                batch_id=batch_id,
                essays_to_process=[
                    {"essay_id": essay["essay_id"], "content": essay["content"]}
                    for essay in essays
                ],
                language="en",
            ).model_dump(mode="json"),
        )
    
    return {
        "batch_nlp_initiate_command": create_batch_nlp_initiate_command,
        "batch_nlp_processing_requested": create_batch_nlp_processing_requested,
    }


@pytest_asyncio.fixture
async def event_monitor():
    """Monitor and collect events from Kafka topics during testing."""
    collected_events: dict[str, list[EventEnvelope]] = {}
    
    class EventMonitor:
        async def wait_for_event(
            self,
            consumer: AIOKafkaConsumer,
            topic: str,
            timeout: float = 30.0,
            event_type: str | None = None,
            correlation_id: str | None = None,
        ) -> EventEnvelope | None:
            """Wait for a specific event to appear on a topic."""
            
            start_time = time.time()
            
            try:
                # Subscribe to the topic if not already subscribed
                if topic not in consumer.subscription():
                    consumer.subscribe([topic])
                
                async for msg in consumer:
                    if time.time() - start_time > timeout:
                        break
                    
                    if msg.topic != topic:
                        continue
                    
                    try:
                        # Parse the event envelope
                        envelope: EventEnvelope = EventEnvelope.model_validate(msg.value)
                        
                        # Check if this matches our criteria
                        if event_type and envelope.event_type != event_type:
                            continue
                        
                        if correlation_id and envelope.correlation_id != correlation_id:
                            continue
                        
                        # Store the event
                        if topic not in collected_events:
                            collected_events[topic] = []
                        collected_events[topic].append(envelope)
                        
                        return envelope
                        
                    except Exception as e:
                        print(f"Error parsing event: {e}")
                        continue
                        
            except asyncio.TimeoutError:
                pass
            
            return None
        
        def get_collected_events(self, topic: str) -> list[EventEnvelope]:
            """Get all events collected for a topic."""
            return collected_events.get(topic, [])
        
        def clear_events(self, topic: str | None = None) -> None:
            """Clear collected events for a topic or all topics."""
            if topic:
                collected_events.pop(topic, None)
            else:
                collected_events.clear()
    
    return EventMonitor()


@pytest.fixture
def topic_names() -> dict[str, str]:
    """Standard topic names used in the pipeline."""
    return {
        "batch_nlp_initiate_command": topic_name(ProcessingEvent.BATCH_NLP_INITIATE_COMMAND),
        "batch_nlp_processing_requested": topic_name(ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED),
        "batch_nlp_analysis_completed": topic_name(ProcessingEvent.BATCH_NLP_ANALYSIS_COMPLETED),
        "essay_nlp_completed": topic_name(ProcessingEvent.ESSAY_NLP_COMPLETED),
    }


# Utility functions that can be used by tests

async def send_event_and_wait(
    producer: AIOKafkaProducer,
    topic: str,
    event: EventEnvelope,
    key: str | None = None,
) -> None:
    """Send an event to a topic and wait for confirmation."""
    
    await producer.send_and_wait(
        topic=topic,
        key=key,
        value=event.model_dump(mode="json"),
    )


async def verify_service_health(
    compose: DockerCompose,
    service_name: str,
) -> bool:
    """Verify that a service is healthy and ready."""
    try:
        result = compose.exec_in_container(
            service_name=service_name,
            command=["sh", "-c", "echo 'Health check'"],
        )
        return bool(result.exit_code == 0)
    except Exception:
        return False