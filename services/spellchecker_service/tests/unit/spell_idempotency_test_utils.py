"""
Shared utilities, fixtures, and mock objects for spell checker idempotency tests.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiokafka import ConsumerRecord
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.status_enums import EssayStatus

from services.spellchecker_service.protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
    SpellLogicProtocol,
)


class MockRedisClient:
    """Mock Redis client for testing idempotency behavior."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []
        self.delete_calls: list[str] = []
        self.should_fail_set = False

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """Mock SETNX operation that tracks calls."""
        self.set_calls.append((key, value, ttl_seconds or 0))

        if self.should_fail_set:
            raise Exception("Redis connection failed")

        if key in self.keys:
            return False  # Key already exists (duplicate)

        self.keys[key] = value
        return True  # Key set successfully (first time)

    async def delete_key(self, key: str) -> int:
        """Mock DELETE operation that tracks calls."""
        self.delete_calls.append(key)
        if key in self.keys:
            del self.keys[key]
            return 1
        return 0

    async def delete(self, *keys: str) -> int:
        """Mock multi-key DELETE operation required by RedisClientProtocol."""
        total_deleted = 0
        for key in keys:
            deleted_count = await self.delete_key(key)
            total_deleted += deleted_count
        return total_deleted

    async def get(self, key: str) -> str | None:
        """Mock GET operation that retrieves values."""
        if self.should_fail_set:  # Simulate full Redis outage
            raise Exception("Redis connection failed")
        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Mock SETEX operation that sets values with TTL."""
        self.keys[key] = value
        return True

    async def ping(self) -> bool:
        """Mock PING operation required by RedisClientProtocol."""
        return True


def create_mock_kafka_message(event_data: dict) -> ConsumerRecord:
    """Create a mock Kafka ConsumerRecord for testing."""
    return ConsumerRecord(
        topic=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED),
        partition=0,
        offset=12345,
        timestamp=None,
        timestamp_type=None,
        key=None,
        value=json.dumps(event_data).encode("utf-8"),
        checksum=None,
        serialized_key_size=None,
        serialized_value_size=None,
        headers=[],
    )


@pytest.fixture
def sample_spellcheck_request_event() -> dict:
    """Sample spell check request event data."""
    essay_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED),
        "event_timestamp": datetime.now(UTC).isoformat(),
        "source_service": "essay_lifecycle_service",
        "correlation_id": correlation_id,
        "data": {
            "event_name": "essay.spellcheck.requested",
            "entity_id": essay_id,
            "entity_type": "essay",
            "parent_id": str(uuid.uuid4()),
            "status": EssayStatus.AWAITING_SPELLCHECK.value,
            "system_metadata": {
                "entity_id": essay_id,
                "entity_type": "essay",
                "parent_id": str(uuid.uuid4()),
                "timestamp": datetime.now(UTC).isoformat(),
                "processing_stage": "pending",
                "event": "essay.spellcheck.requested",
            },
            "text_storage_id": "storage-123",
            "language": "en",
        },
    }


@pytest.fixture
def mock_boundary_services() -> tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    """Create mock boundary services (external dependencies only)."""
    http_session = AsyncMock()
    content_client = AsyncMock(spec=ContentClientProtocol)
    content_client.fetch_content.return_value = (
        "This is a sample essay text with some misspelled words"
    )
    result_store = AsyncMock(spec=ResultStoreProtocol)
    result_store.store_content.return_value = "corrected-storage-456"
    event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)
    event_publisher.publish_spellcheck_result.return_value = None
    kafka_bus = AsyncMock()
    return http_session, content_client, result_store, event_publisher, kafka_bus


@pytest.fixture
def real_spell_logic(
    mock_boundary_services: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock],
) -> SpellLogicProtocol:
    """Create real spell logic implementation for testing business logic."""
    _, _, result_store, _, _ = mock_boundary_services
    from services.spellchecker_service.implementations.spell_logic_impl import (
        DefaultSpellLogic,
    )

    return DefaultSpellLogic(
        result_store=result_store,
        http_session=mock_boundary_services[0],
    )
