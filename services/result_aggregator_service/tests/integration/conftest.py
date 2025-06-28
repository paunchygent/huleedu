"""Shared fixtures for integration tests."""

import json
from typing import Any, Dict, Generator, List, Optional
from unittest.mock import AsyncMock

import pytest
from aiokafka import ConsumerRecord
from prometheus_client import REGISTRY

from common_core.events import EventEnvelope
from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.kafka_consumer import ResultAggregatorKafkaConsumer
from services.result_aggregator_service.metrics import ResultAggregatorMetrics
from services.result_aggregator_service.protocols import EventProcessorProtocol


class MockRedisClient:
    """Mock Redis client for testing idempotency."""

    def __init__(self) -> None:
        self.keys: Dict[str, str] = {}
        self.set_calls: List[tuple[str, str, Optional[int]]] = []
        self.delete_calls: List[str] = []

    async def set_if_not_exists(
        self, key: str, value: Any, ttl_seconds: Optional[int] = None
    ) -> bool:
        """Mock Redis SETNX operation."""
        self.set_calls.append((key, str(value), ttl_seconds))
        if key in self.keys:
            return False
        self.keys[key] = str(value)
        return True

    async def delete_key(self, key: str) -> int:
        """Mock Redis DELETE operation."""
        self.delete_calls.append(key)
        if key in self.keys:
            del self.keys[key]
            return 1
        return 0

    async def get(self, key: str) -> Optional[str]:
        """Mock GET operation."""
        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Mock SETEX operation."""
        self.keys[key] = value
        return True


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        SERVICE_NAME="test-result-aggregator",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        KAFKA_CONSUMER_GROUP_ID="test-group",
        KAFKA_AUTO_OFFSET_RESET="earliest",
        KAFKA_MAX_POLL_RECORDS=100,
        KAFKA_SESSION_TIMEOUT_MS=30000,
    )


@pytest.fixture
def mock_event_processor() -> AsyncMock:
    """Create mock event processor."""
    return AsyncMock(spec=EventProcessorProtocol)


@pytest.fixture(autouse=True)
def clear_prometheus_registry() -> Generator[None, None, None]:
    """Clear Prometheus registry before each test."""
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass
    yield


@pytest.fixture
def mock_metrics() -> ResultAggregatorMetrics:
    """Create metrics instance."""
    return ResultAggregatorMetrics()


@pytest.fixture
def mock_redis_client() -> MockRedisClient:
    """Create mock Redis client."""
    return MockRedisClient()


@pytest.fixture
def kafka_consumer(
    settings: Settings,
    mock_event_processor: AsyncMock,
    mock_metrics: ResultAggregatorMetrics,
    mock_redis_client: MockRedisClient,
) -> ResultAggregatorKafkaConsumer:
    """Create Kafka consumer instance."""
    return ResultAggregatorKafkaConsumer(
        settings=settings,
        event_processor=mock_event_processor,
        metrics=mock_metrics,
        redis_client=mock_redis_client,  # type: ignore[arg-type]
    )


def create_kafka_record(
    topic: str, event_envelope: EventEnvelope[Any], offset: int = 12345
) -> ConsumerRecord:
    """Create a mock Kafka ConsumerRecord."""
    # Use Pydantic's model_dump with mode="json" to properly serialize all fields
    envelope_dict = event_envelope.model_dump(mode="json")

    return ConsumerRecord(
        topic=topic,
        partition=0,
        offset=offset,
        timestamp=None,
        timestamp_type=None,
        key=None,
        value=json.dumps(envelope_dict).encode("utf-8"),
        checksum=None,
        serialized_key_size=None,
        serialized_value_size=None,
        headers=[],
    )
