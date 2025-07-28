"""
Shared fixtures for functional tests.

This includes diagnostic fixtures for deep testing of distributed system state.
"""

from typing import AsyncGenerator, List

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

    # Use verified cleanup with retry logic to handle race conditions
    await distributed_state_manager.ensure_verified_clean_state("comprehensive_test")
    yield


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


@pytest.fixture
async def verify_redis_is_pristine(clean_distributed_state, get_redis_client):
    """
    A diagnostic fixture that runs AFTER the main cleanup
    to verify that all ELS idempotency keys are truly gone.

    This fixture will FAIL the test immediately if Redis is not clean,
    helping us identify whether the DistributedStateManager is working correctly.
    """
    # Ensure clean_distributed_state ran first
    _ = clean_distributed_state

    logger.info("🔬 DIAGNOSTIC: Verifying pristine state of Redis for ELS keys...")

    redis_client = get_redis_client
    found_keys: List[str] = []

    # Use SCAN to find all v2 idempotency keys
    async for key in redis_client.scan_iter("huleedu:idempotency:v2:*"):
        if isinstance(key, bytes):
            found_keys.append(key.decode("utf-8"))
        else:
            found_keys.append(str(key))

    total_found = len(found_keys)

    if total_found > 0:
        all_keys = found_keys
        logger.critical(
            f"🚨 DIAGNOSTIC FAILURE: Found {total_found} ELS idempotency keys "
            f"in Redis AFTER cleanup! Keys found: {all_keys[:10]}"
            f"{'...' if len(all_keys) > 10 else ''}"
        )
        # This assertion will halt the test immediately with detailed info
        assert total_found == 0, (
            f"Redis was not clean for ELS after setup. Found {total_found} keys: "
            f"huleedu:idempotency:v2:* = {len(found_keys)}. "
            f"Sample keys: {all_keys[:5]}"
        )
    else:
        logger.info("✅ DIAGNOSTIC SUCCESS: Redis is pristine for ELS.")

    yield
