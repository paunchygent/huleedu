from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Dict

import pytest

from ._helpers_idempotency import MockRedisClient


@pytest.fixture
def mock_redis_client() -> MockRedisClient:
    """Provide a mock Redis client for idempotency tests."""
    return MockRedisClient()


@pytest.fixture
def sample_event_data() -> Dict[str, str]:
    """Provide sample Kafka event data for testing."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "test.event.v1",
        "event_timestamp": datetime.now(UTC).isoformat(),
        "source_service": "test-service",
        "correlation_id": str(uuid.uuid4()),
        "data": {"test_field": "test_value", "batch_id": "test-batch-123"},
    }


@pytest.fixture
def swedish_source_service() -> str:
    """Swedish characters to validate locale handling where applicable."""
    return "fil_tjänst_ÅÄÖ"

