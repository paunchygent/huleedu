"""
Shared fixtures for functional tests.

This includes diagnostic fixtures for deep testing of distributed system state.
"""

from typing import AsyncGenerator

import pytest
import redis.asyncio as aioredis
from huleedu_service_libs.logging_utils import create_service_logger

# Removed unused import - now using distributed_state_manager directly

logger = create_service_logger("test.functional.conftest")


@pytest.fixture
async def clean_distributed_state():
    """
    Fixture that ensures clean distributed state before tests.

    This calls the DistributedStateManager to clean Redis and Kafka state
    with verification and retry logic to handle timing issues.
    """
    from tests.utils.distributed_state_manager import distributed_state_manager

    try:
        # Use verified cleanup with retry logic to handle race conditions
        await distributed_state_manager.ensure_verified_clean_state("comprehensive_test")
        yield
    except RuntimeError as e:
        # Provide helpful error message if Docker services aren't running
        pytest.fail(
            f"\n{'=' * 60}\n"
            f"🚨 E2E TEST INFRASTRUCTURE ERROR\n\n"
            f"{str(e)}\n\n"
            f"To run E2E tests, ensure all services are running:\n"
            f"  docker compose up -d\n"
            f"  docker compose ps  # verify all are healthy\n"
            f"{'=' * 60}\n"
        )


@pytest.fixture
async def get_redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    """
    Get a direct Redis client for diagnostic purposes.

    Uses the same Redis instance as the services but with a dedicated client.
    """
    redis_url = "redis://localhost:6379"  # Direct connection to our Docker Redis
    client = aioredis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )

    try:
        # Verify connection
        await client.ping()
        logger.info("🔗 Diagnostic Redis client connected")
        yield client
    finally:
        await client.aclose()
        logger.info("🔌 Diagnostic Redis client disconnected")
