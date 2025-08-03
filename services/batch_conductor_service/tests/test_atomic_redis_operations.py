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
        mock_client.setex = AsyncMock(return_value=True)  # For fallback operations
        mock_client.delete_key = AsyncMock(return_value=1)  # For fallback operations

        # Create mock pipeline for transaction operations
        mock_pipeline = AsyncMock()
        mock_pipeline.multi = lambda: None  # Sync method, no return
        mock_pipeline.setex = lambda key, ttl, value: None  # Sync method, no return
        mock_pipeline.delete = lambda key: None  # Sync method, no return
        mock_pipeline.execute = AsyncMock(
            return_value=[True, 1]
        )  # Async method, returns transaction results

        # Redis client returns the pipeline when creating transaction
        mock_client.create_transaction_pipeline = AsyncMock(return_value=mock_pipeline)

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

        result = await repository.record_essay_step_completion(
            batch_id, essay_id, step_name, metadata
        )

        assert result is True

        # Verify transaction pipeline was created and executed
        mock_redis_client.create_transaction_pipeline.assert_called_once_with(
            f"bcs:essay_state:{batch_id}:{essay_id}"
        )

        # Get the pipeline that was returned and verify execute was called
        pipeline = mock_redis_client.create_transaction_pipeline.return_value
        pipeline.execute.assert_called_once()

    async def test_atomic_operation_retry_on_watch_failure(self, repository, mock_redis_client):
        """Test retry logic when watched key changes."""
        batch_id = "test-batch-002"
        essay_id = "essay-002"
        step_name = "nlp"
        metadata = {"status": "success"}

        # Create pipelines for each retry attempt
        mock_pipeline_1 = AsyncMock()
        mock_pipeline_1.multi = lambda: None
        mock_pipeline_1.setex = lambda key, ttl, value: None
        mock_pipeline_1.delete = lambda key: None
        mock_pipeline_1.execute = AsyncMock(return_value=None)  # First attempt fails

        mock_pipeline_2 = AsyncMock()
        mock_pipeline_2.multi = lambda: None
        mock_pipeline_2.setex = lambda key, ttl, value: None
        mock_pipeline_2.delete = lambda key: None
        mock_pipeline_2.execute = AsyncMock(return_value=[True, 1])  # Second attempt succeeds

        # Mock create_transaction_pipeline to return different pipelines for retries
        mock_redis_client.create_transaction_pipeline.side_effect = [
            mock_pipeline_1,
            mock_pipeline_2,
        ]

        result = await repository.record_essay_step_completion(
            batch_id, essay_id, step_name, metadata
        )

        assert result is True

        # Verify retry occurred - pipeline was created twice
        assert mock_redis_client.create_transaction_pipeline.call_count == 2
        mock_pipeline_1.execute.assert_called_once()
        mock_pipeline_2.execute.assert_called_once()

    async def test_atomic_operation_fallback_after_max_retries(self, repository, mock_redis_client):
        """Test fallback to non-atomic operation after max retries."""
        batch_id = "test-batch-003"
        essay_id = "essay-003"
        step_name = "ai_feedback"
        metadata = {"status": "success"}

        # Create failing pipelines for each retry attempt
        failing_pipelines = []
        for _ in range(5):
            mock_pipeline = AsyncMock()
            mock_pipeline.multi = lambda: None
            mock_pipeline.setex = lambda key, ttl, value: None
            mock_pipeline.delete = lambda key: None
            mock_pipeline.execute = AsyncMock(return_value=None)  # Transaction fails
            failing_pipelines.append(mock_pipeline)

        # Mock create_transaction_pipeline to return failing pipelines
        mock_redis_client.create_transaction_pipeline.side_effect = failing_pipelines

        result = await repository.record_essay_step_completion(
            batch_id, essay_id, step_name, metadata
        )

        assert result is True  # Should succeed via fallback

        # Verify max retries were attempted (5 attempts)
        assert mock_redis_client.create_transaction_pipeline.call_count == 5
        for pipeline in failing_pipelines:
            pipeline.execute.assert_called_once()

        # Verify fallback to non-atomic operation occurred
        mock_redis_client.setex.assert_called()  # Fallback operation
        mock_redis_client.delete_key.assert_called()  # Fallback operation

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

        # Verify no transaction pipeline was created due to idempotency
        mock_redis_client.create_transaction_pipeline.assert_not_called()
        # Verify no fallback operations occurred
        mock_redis_client.setex.assert_not_called()
        mock_redis_client.delete_key.assert_not_called()

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
        assert mock_redis_client.create_transaction_pipeline.call_count >= 3
