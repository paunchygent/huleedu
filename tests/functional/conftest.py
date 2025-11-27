"""
Shared fixtures for functional tests.

This includes diagnostic fixtures for deep testing of distributed system state
and session-level resource management for optimal performance.
"""

import asyncio
import logging
import os
from typing import AsyncGenerator

import aiohttp
import pytest
import redis.asyncio as aioredis
from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)

from tests.functional.comprehensive_pipeline_utils import PIPELINE_TOPICS
from tests.utils.kafka_test_manager import KafkaTestManager, create_kafka_test_config
from tests.utils.service_test_manager import ServiceTestManager

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

READINESS_TIMEOUT_SECONDS = int(os.getenv("FUNCTIONAL_READINESS_TIMEOUT", "60"))
READINESS_RETRY_SECONDS = int(os.getenv("FUNCTIONAL_READINESS_RETRY", "3"))
REDIS_URL = os.getenv("FUNCTIONAL_REDIS_URL", "redis://localhost:6379")
_MOCK_LLM_ENV_VARS = ("LLM_PROVIDER_SERVICE_USE_MOCK_LLM", "USE_MOCK_LLM")

# Aggregate topics that functional tests commonly touch (pipeline + entitlements + student matching)
_DEFAULT_KAFKA_TOPICS: set[str] = set(create_kafka_test_config().topics.values()) | set(
    PIPELINE_TOPICS.values()
)
_DEFAULT_KAFKA_TOPICS.update(
    {
        "huleedu.entitlements.credit.balance.changed.v1",
        "huleedu.entitlements.usage.recorded.v1",
        "huleedu.batch.student.matching.initiate.command.v1",
        "huleedu.batch.student.matching.requested.v1",
        "huleedu.batch.author.matches.suggested.v1",
        "huleedu.class.student.associations.confirmed.v1",
        "huleedu.batch.pipeline.compatibility_failed.v1",
    }
)


# NOTE: The clean_distributed_state fixture has been removed in favor of explicit cleanup calls
# Tests now use distributed_state_manager.quick_redis_cleanup() directly for better control


def _mock_llm_enabled() -> bool:
    """Return True when mock LLM mode is enabled (default)."""
    provided_flags: list[str] = []
    for var in _MOCK_LLM_ENV_VARS:
        flag = os.getenv(var)
        if flag is not None:
            provided_flags.append(flag)
    if not provided_flags:
        return True  # docker-compose defaults keep mock mode on
    return all(flag.lower() not in {"false", "0", "no"} for flag in provided_flags)


@pytest.fixture(scope="session", autouse=True)
def enforce_mock_llm_mode() -> None:
    """
    Prevent functional runs from hitting real LLM providers.

    Skip the suite when mock mode is explicitly disabled unless ALLOW_REAL_LLM_FUNCTIONAL=1
    is set. This keeps CJ runs fast and deterministic.
    """
    if os.getenv("ALLOW_REAL_LLM_FUNCTIONAL", "").lower() in {"1", "true", "yes"}:
        return
    if not _mock_llm_enabled():
        pytest.skip(
            "Mock LLM must be enabled for functional suite. "
            "Set USE_MOCK_LLM=true (or LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true) "
            "or export ALLOW_REAL_LLM_FUNCTIONAL=1 to bypass."
        )


@pytest.fixture(scope="session", autouse=True)
async def ensure_services_ready() -> AsyncGenerator[None, None]:
    """
    Wait for core services to report healthy before running functional tests.

    Uses ServiceTestManager to validate /healthz endpoints with bounded retries.
    Skips the suite with a clear message if the functional stack is not ready.
    """
    manager = ServiceTestManager()
    deadline = asyncio.get_event_loop().time() + READINESS_TIMEOUT_SECONDS
    last_error: Exception | None = None

    while asyncio.get_event_loop().time() < deadline:
        try:
            await manager.get_validated_endpoints(force_revalidation=True)
            logger.info("✅ Functional stack healthy, starting tests")
            break
        except Exception as exc:  # noqa: BLE001 - broad to capture readiness failures
            last_error = exc
            await asyncio.sleep(READINESS_RETRY_SECONDS)
    else:
        pytest.skip(f"Functional stack not ready after {READINESS_TIMEOUT_SECONDS}s: {last_error}")

    try:
        yield
    finally:
        logger.info("🏁 Functional stack readiness check complete")


@pytest.fixture(scope="session", autouse=True)
async def ensure_kafka_topics() -> AsyncGenerator[None, None]:
    """
    Pre-create Kafka topics to avoid UnknownTopicOrPartition errors during functional runs.
    """
    manager = KafkaTestManager()
    topics = sorted(_DEFAULT_KAFKA_TOPICS)
    await manager.ensure_topics(topics, num_partitions=3)
    logger.info("📡 Kafka topics ensured for functional suite")
    yield


async def _delete_prefixed_keys(client: aioredis.Redis, prefixes: list[str]) -> None:
    """Delete keys matching the provided prefix patterns."""
    for prefix in prefixes:
        keys = await client.keys(prefix)
        if keys:
            await client.delete(*keys)
            logger.info(f"🧹 Cleared {len(keys)} Redis keys with prefix '{prefix}'")


@pytest.fixture(scope="session", autouse=True)
async def cleanup_redis_test_keys() -> AsyncGenerator[None, None]:
    """
    Ensure test-prefixed Redis keys do not leak between runs.
    """
    client = aioredis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    try:
        await _delete_prefixed_keys(client, ["test:*", "ws:*"])
        yield
        await _delete_prefixed_keys(client, ["test:*", "ws:*"])
    finally:
        await client.aclose()
        logger.info("🔌 Redis test client disconnected")


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


@pytest.fixture
async def http_session() -> AsyncGenerator[aiohttp.ClientSession, None]:
    """Provide an aiohttp ClientSession for functional tests."""
    async with aiohttp.ClientSession() as session:
        yield session
