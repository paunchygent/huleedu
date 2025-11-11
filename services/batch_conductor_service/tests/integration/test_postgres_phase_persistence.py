"""
Integration tests for PostgreSQL phase persistence in BCS.

Tests the permanent storage of phase completions and cache-aside pattern
with Redis and PostgreSQL working together.
"""

from __future__ import annotations

import asyncio

import pytest

from huleedu_service_libs.redis_client import RedisClient
from services.batch_conductor_service.config import Settings
from services.batch_conductor_service.implementations.postgres_batch_state_repository import (
    PostgreSQLBatchStateRepositoryImpl,
)
from services.batch_conductor_service.implementations.redis_batch_state_repository import (
    RedisCachedBatchStateRepositoryImpl,
)


@pytest.fixture
async def redis_client():
    """Provide a test Redis client."""
    client = RedisClient(
        client_id="test-bcs",
        redis_url="redis://localhost:6379",
    )
    await client.start()

    # Clear any test data
    await client.delete("bcs:batch:*")

    yield client

    await client.stop()


@pytest.fixture
async def settings():
    """Provide test settings."""
    return Settings(
        REDIS_TTL_SECONDS=7,  # Short TTL for testing
        ENVIRONMENT="testing",
    )


@pytest.fixture
async def postgres_repo(settings):
    """Provide a test PostgreSQL repository."""
    repo = PostgreSQLBatchStateRepositoryImpl(database_url=settings.DATABASE_URL)

    # Clean up any existing test data
    from sqlalchemy import text

    async with repo.async_session() as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM phase_completions WHERE batch_id LIKE 'test-%'")
            )
            await session.commit()

    yield repo

    await repo.close()


@pytest.fixture
async def redis_repo(redis_client, postgres_repo):
    """Provide a Redis repository with PostgreSQL fallback."""
    return RedisCachedBatchStateRepositoryImpl(
        redis_client=redis_client,
        postgres_repository=postgres_repo,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_phase_completion_persists_in_both_stores(redis_repo, redis_client):
    """Test that phase completions are stored in both Redis and PostgreSQL."""
    batch_id = "test-batch-001"
    phase_name = "spellcheck"

    # Record phase completion
    result = await redis_repo.record_batch_phase_completion(
        batch_id=batch_id,
        phase_name=phase_name,
        completed=True,
    )

    assert result is True

    # Verify in Redis
    redis_key = f"bcs:batch:{batch_id}:phases"
    redis_data = await redis_client.hgetall(redis_key)
    assert redis_data[phase_name] == "completed"

    # Verify in PostgreSQL by querying through Redis repo (which has postgres fallback)
    # Clear Redis first to force PostgreSQL query
    await redis_client.delete(redis_key)
    pg_phases = await redis_repo.get_completed_phases(batch_id)
    assert phase_name in pg_phases


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgresql_fallback_when_redis_empty(redis_repo, redis_client):
    """Test that PostgreSQL is queried when Redis cache is empty."""
    batch_id = "test-batch-002"
    phases = ["spellcheck", "nlp_analysis", "ai_feedback"]

    # Record multiple phase completions
    for phase in phases:
        await redis_repo.record_batch_phase_completion(
            batch_id=batch_id,
            phase_name=phase,
            completed=True,
        )

    # Clear Redis cache to simulate TTL expiry
    redis_key = f"bcs:batch:{batch_id}:phases"
    await redis_client.delete(redis_key)

    # Verify Redis is empty
    redis_data = await redis_client.hgetall(redis_key)
    assert redis_data == {}

    # Query through Redis repo - should fallback to PostgreSQL
    completed_phases = await redis_repo.get_completed_phases(batch_id)
    assert completed_phases == set(phases)

    # Verify Redis was repopulated
    redis_data = await redis_client.hgetall(redis_key)
    assert len(redis_data) == 3
    assert all(redis_data[phase] == "completed" for phase in phases)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_idempotent_phase_recording(redis_repo, postgres_repo):
    """Test that recording the same phase multiple times is idempotent."""
    batch_id = "test-batch-004"
    phase_name = "spellcheck"

    # Record the same phase completion multiple times
    for _ in range(3):
        result = await redis_repo.record_batch_phase_completion(
            batch_id=batch_id,
            phase_name=phase_name,
            completed=True,
        )
        assert result is True

    # Should only have one record in PostgreSQL
    pg_phases = await postgres_repo.get_completed_phases(batch_id)
    assert pg_phases == {phase_name}

    # Verify only one entry in the database
    from sqlalchemy import text

    async with postgres_repo.async_session() as session:
        result = await session.execute(
            text(f"SELECT COUNT(*) FROM phase_completions WHERE batch_id = '{batch_id}'")
        )
        count = result.scalar()
        assert count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_pipeline_dependency_resolution(redis_repo, redis_client):
    """Test that dependency resolution works for multi-pipeline scenarios."""
    batch_id = "test-batch-005"

    # Simulate first pipeline run (e.g., spellcheck pipeline)
    await redis_repo.record_batch_phase_completion(batch_id, "spellcheck", True)
    await redis_repo.record_batch_phase_completion(batch_id, "nlp_analysis", True)

    # Clear Redis to simulate time passing
    await redis_client.delete(f"bcs:batch:{batch_id}:phases")

    # Simulate second pipeline run weeks later (e.g., ai_feedback pipeline)
    # Should be able to see previously completed phases
    completed_phases = await redis_repo.get_completed_phases(batch_id)
    assert "spellcheck" in completed_phases
    assert "nlp_analysis" in completed_phases

    # Add new phase from second pipeline
    await redis_repo.record_batch_phase_completion(batch_id, "ai_feedback", True)

    # Verify all phases are now available
    all_phases = await redis_repo.get_completed_phases(batch_id)
    assert all_phases == {"spellcheck", "nlp_analysis", "ai_feedback"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_phase_recording(redis_repo):
    """Test that concurrent phase recordings don't cause race conditions."""
    batch_id = "test-batch-006"
    phases = [f"phase_{i}" for i in range(10)]

    # Record phases concurrently
    tasks = [redis_repo.record_batch_phase_completion(batch_id, phase, True) for phase in phases]
    results = await asyncio.gather(*tasks)

    assert all(results)

    # Verify all phases were recorded
    completed_phases = await redis_repo.get_completed_phases(batch_id)
    assert completed_phases == set(phases)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_phase_not_included_in_completed(redis_repo):
    """Test that failed phases are not returned as completed."""
    batch_id = "test-batch-007"

    # Record successful phase
    await redis_repo.record_batch_phase_completion(batch_id, "spellcheck", True)

    # Record failed phase
    await redis_repo.record_batch_phase_completion(batch_id, "ai_feedback", False)

    # Only successful phase should be returned
    completed_phases = await redis_repo.get_completed_phases(batch_id)
    assert completed_phases == {"spellcheck"}
    assert "ai_feedback" not in completed_phases
