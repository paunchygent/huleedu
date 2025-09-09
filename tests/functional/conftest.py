"""
Shared fixtures for functional tests.

This includes diagnostic fixtures for deep testing of distributed system state
and session-level resource management for optimal performance.
"""

import logging
import os
from typing import AsyncGenerator

import pytest
import redis.asyncio as aioredis
from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)

# Configure structlog once for the functional test session
# Avoid duplicate log output under pytest by removing any handler
# added by basicConfig during configure_service_logging.
_root = logging.getLogger()
_pre_handlers = list(_root.handlers)
configure_service_logging(
    service_name="tests",
    environment="development",
    log_level=os.getenv("TEST_LOG_LEVEL", "INFO"),
)
for _h in list(_root.handlers):
    if _h not in _pre_handlers:
        _root.removeHandler(_h)

logger = create_service_logger("test.functional.conftest")


# NOTE: The clean_distributed_state fixture has been removed in favor of explicit cleanup calls
# Tests now use distributed_state_manager.quick_redis_cleanup() directly for better control


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


@pytest.fixture(scope="session", autouse=True)
async def cleanup_session_resources():
    """
    Session-scoped fixture to clean up shared resources after all tests complete.

    This includes Kafka consumer pools and other session-level resources to prevent
    resource leaks and ensure clean test environment shutdown.
    """
    # Session setup (none needed currently)
    yield

    # Session cleanup
    try:
        from tests.utils.kafka_test_manager import _kafka_consumer_pool

        if _kafka_consumer_pool is not None:
            await _kafka_consumer_pool.cleanup_pool()
            logger.info("🧹 Session cleanup: Kafka consumer pool cleaned up")
    except Exception as e:
        logger.warning(f"⚠️ Session cleanup error: {e}")

    logger.info("✅ Session cleanup completed")
