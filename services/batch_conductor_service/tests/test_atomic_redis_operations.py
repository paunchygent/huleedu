"""
Test atomic Redis operations in BCS repository.

Verifies that the WATCH/MULTI/EXEC pattern works correctly for race condition safety.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from services.batch_conductor_service.implementations.batch_state_repository_impl import (
    RedisCachedBatchStateRepositoryImpl,
)


class TestAtomicRedisOperations:
    """Test atomic Redis operations for essay step completion."""

    @pytest.fixture
    async def mock_redis_client(self):
        """Create a mock Redis client that supports atomic operations."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)  # No existing data
        mock_client.setex = AsyncMock(return_value=True)
        mock_client.delete_key = AsyncMock(return_value=1)
        mock_client.watch = AsyncMock(return_value=True)
        mock_client.multi = AsyncMock(return_value=True)
        mock_client.exec = AsyncMock(return_value=[True, 1])  # Successful transaction
        mock_client.unwatch = AsyncMock(return_value=True)
        return mock_client

    @pytest.fixture
    async def repository(self, mock_redis_client):
        """Create a repository with mocked Redis client."""
        return RedisCachedBatchStateRepositoryImpl(
            redis_client=mock_redis_client,
            postgres_repository=None,
        )

    async def test_atomic_operation_success_first_attempt(self, repository, mock_redis_client):
        """Test successful atomic operation on first attempt."""
        batch_id = "test-batch-001"
        essay_id = "essay-001"
        step_name = "spellcheck"
        metadata = {"status": "success"}

        # Mock Redis to return successful transaction on first attempt
        mock_redis_client.exec.return_value = [True, 1]  # Transaction succeeded

        result = await repository.record_essay_step_completion(
            batch_id, essay_id, step_name, metadata
        )

        assert result is True

        # Verify atomic operations were called
        mock_redis_client.watch.assert_called_once_with(f"bcs:essay_state:{batch_id}:{essay_id}")
        mock_redis_client.multi.assert_called_once()
        mock_redis_client.exec.assert_called_once()

        # Verify setex and delete were called during transaction
        assert mock_redis_client.setex.call_count == 1
        assert mock_redis_client.delete_key.call_count == 1

    async def test_atomic_operation_retry_on_watch_failure(self, repository, mock_redis_client):
        """Test retry logic when watched key changes."""
        batch_id = "test-batch-002"
        essay_id = "essay-002"
        step_name = "nlp"
        metadata = {"status": "success"}

        # Mock Redis to fail first attempt (watched key changed), succeed second
        mock_redis_client.exec.side_effect = [
            None,  # First attempt: transaction discarded
            [True, 1],  # Second attempt: transaction succeeded
        ]

        result = await repository.record_essay_step_completion(
            batch_id, essay_id, step_name, metadata
        )

        assert result is True

        # Verify retry occurred
        assert mock_redis_client.watch.call_count == 2
        assert mock_redis_client.multi.call_count == 2
        assert mock_redis_client.exec.call_count == 2

    async def test_atomic_operation_fallback_after_max_retries(self, repository, mock_redis_client):
        """Test fallback to non-atomic operation after max retries."""
        batch_id = "test-batch-003"
        essay_id = "essay-003"
        step_name = "ai_feedback"
        metadata = {"status": "success"}

        # Mock Redis to always fail atomic operations (watched key keeps changing)
        mock_redis_client.exec.return_value = None  # Always return None (discarded)

        result = await repository.record_essay_step_completion(
            batch_id, essay_id, step_name, metadata
        )

        assert result is True  # Should succeed via fallback

        # Verify max retries were attempted (5 attempts)
        assert mock_redis_client.watch.call_count == 5
        assert mock_redis_client.multi.call_count == 5
        assert mock_redis_client.exec.call_count == 5

        # Verify fallback to non-atomic operation occurred
        # Non-atomic operation should call setex outside of transaction
        total_setex_calls = mock_redis_client.setex.call_count
        assert total_setex_calls >= 6  # 5 atomic attempts + 1 fallback

    async def test_atomic_operation_idempotency(self, repository, mock_redis_client):
        """Test that atomic operation handles idempotency correctly."""
        batch_id = "test-batch-004"
        essay_id = "essay-004"
        step_name = "spellcheck"

        # Mock Redis to return existing essay state with step already completed
        mock_redis_client.get.return_value = (
            '{"completed_steps": ["spellcheck"], '
            '"step_metadata": {"spellcheck": {"status": "success"}}, '
            '"created_at": "2025-06-18T20:00:00Z", '
            '"last_updated": "2025-06-18T20:00:00Z"}'
        )

        result = await repository.record_essay_step_completion(batch_id, essay_id, step_name, {})

        assert result is True

        # Verify watch was called but transaction was not executed (idempotency)
        mock_redis_client.watch.assert_called_once()
        mock_redis_client.unwatch.assert_called_once()  # Should unwatch when skipping
        mock_redis_client.multi.assert_not_called()  # Transaction not needed
        mock_redis_client.exec.assert_not_called()

    async def test_concurrent_updates_simulation(self, mock_redis_client):
        """Test concurrent updates to the same essay state."""
        repository = RedisCachedBatchStateRepositoryImpl(
            redis_client=mock_redis_client,
            postgres_repository=None,
        )

        batch_id = "test-batch-005"
        essay_id = "essay-005"

        # Simulate concurrent updates
        tasks = []
        for i in range(3):
            step_name = f"step_{i}"
            task = repository.record_essay_step_completion(
                batch_id, essay_id, step_name, {"step": i}
            )
            tasks.append(task)

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks)

        # All operations should succeed
        assert all(results)

        # Verify atomic operations were used for each
        assert mock_redis_client.watch.call_count >= 3
        assert mock_redis_client.multi.call_count >= 3
