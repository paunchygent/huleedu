"""
Shared fixtures for integration tests.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from huleedu_service_libs.redis_client import RedisClient
from services.batch_conductor_service.implementations.postgres_batch_state_repository import (
    PostgreSQLBatchStateRepositoryImpl,
)
from services.batch_conductor_service.implementations.redis_batch_state_repository import (
    RedisCachedBatchStateRepositoryImpl,
)


@pytest_asyncio.fixture
async def redis_client():
    """Provide a test Redis client."""
    client = RedisClient(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        client_id="test-bcs",
    )
    await client.start()
    yield client
    # Cleanup: Clear test data
    await client.client.flushdb()
    await client.stop()


@pytest_asyncio.fixture
async def postgres_repo():
    """Provide a test PostgreSQL repository."""
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://huleedu_user:huleedu_pass@localhost:5441/huleedu_batch_conductor"
    )
    repo = PostgreSQLBatchStateRepositoryImpl(database_url=database_url)
    yield repo
    # Cleanup: Clear test data
    from sqlalchemy import text
    async with repo.engine.begin() as conn:
        await conn.execute(text("DELETE FROM phase_completions WHERE batch_id LIKE 'test-%'"))
    await repo.engine.dispose()


@pytest_asyncio.fixture
async def redis_repo(redis_client, postgres_repo):
    """Provide a Redis repository with PostgreSQL fallback."""
    return RedisCachedBatchStateRepositoryImpl(
        redis_client=redis_client,
        postgres_repository=postgres_repo,
    )


@pytest.fixture
async def mock_kafka_producer():
    """Mock Kafka producer for testing event publishing."""
    producer = AsyncMock()
    producer.send.return_value = AsyncMock()
    producer.flush.return_value = None
    return producer