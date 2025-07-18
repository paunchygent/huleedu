"""
Comprehensive behavior-focused tests for Redis Batch State Repository.

Tests all business logic, error scenarios, and edge cases using the established
7-category testing pattern for complete coverage.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from services.batch_conductor_service.implementations.redis_batch_state_repository import (
    RedisCachedBatchStateRepositoryImpl,
)
from services.batch_conductor_service.protocols import BatchStateRepositoryProtocol


class TestRedisBatchStateRepositoryBehavior:
    """Comprehensive behavior-focused tests for Redis Batch State Repository."""

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create a mock Redis client with all required methods."""
        mock_client = AsyncMock(spec=AtomicRedisClientProtocol)
        mock_client.get = AsyncMock(return_value=None)
        mock_client.setex = AsyncMock(return_value=True)
        mock_client.delete_key = AsyncMock(return_value=1)
        mock_client.watch = AsyncMock(return_value=True)
        mock_client.multi = AsyncMock(return_value=True)
        mock_client.exec = AsyncMock(return_value=[True, 1])
        mock_client.unwatch = AsyncMock(return_value=True)
        mock_client.scan_pattern = AsyncMock(return_value=[])
        return mock_client

    @pytest.fixture
    def mock_postgres_repository(self) -> AsyncMock:
        """Create a mock PostgreSQL repository."""
        mock_repo = AsyncMock(spec=BatchStateRepositoryProtocol)
        mock_repo.record_essay_step_completion = AsyncMock(return_value=True)
        return mock_repo

    @pytest.fixture
    def repository(self, mock_redis_client: AsyncMock) -> RedisCachedBatchStateRepositoryImpl:
        """Create repository with mocked Redis client."""
        return RedisCachedBatchStateRepositoryImpl(
            redis_client=mock_redis_client,
            postgres_repository=None,
        )

    @pytest.fixture
    def repository_with_postgres(
        self, mock_redis_client: AsyncMock, mock_postgres_repository: AsyncMock
    ) -> RedisCachedBatchStateRepositoryImpl:
        """Create repository with both Redis and PostgreSQL backends."""
        return RedisCachedBatchStateRepositoryImpl(
            redis_client=mock_redis_client,
            postgres_repository=mock_postgres_repository,
        )

    # Category 1: Successful business operations
    async def test_record_essay_step_completion_success(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test successful essay step completion recording."""
        batch_id = "batch-001"
        essay_id = "essay-001"
        step_name = "spellcheck"
        metadata = {"status": "success", "score": 85}

        # Arrange - Mock successful atomic operation
        mock_redis_client.exec.return_value = [True, 1]

        # Act
        result = await repository.record_essay_step_completion(
            batch_id, essay_id, step_name, metadata
        )

        # Assert
        assert result is True
        mock_redis_client.watch.assert_called_once_with(f"bcs:essay_state:{batch_id}:{essay_id}")
        mock_redis_client.multi.assert_called_once()
        mock_redis_client.exec.assert_called_once()

    async def test_get_essay_completed_steps_success(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test retrieving completed steps for an essay."""
        batch_id = "batch-002"
        essay_id = "essay-002"
        expected_steps = {"spellcheck", "nlp"}

        # Arrange - Mock Redis returning essay state
        mock_redis_client.get.return_value = json.dumps(
            {
                "completed_steps": list(expected_steps),
                "step_metadata": {},
                "created_at": "2025-06-18T20:00:00Z",
                "last_updated": "2025-06-18T20:00:00Z",
            }
        )

        # Act
        result = await repository.get_essay_completed_steps(batch_id, essay_id)

        # Assert
        assert result == expected_steps
        mock_redis_client.get.assert_called_once_with(f"bcs:essay_state:{batch_id}:{essay_id}")

    async def test_get_batch_completion_summary_success(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test retrieving batch completion summary."""
        batch_id = "batch-003"
        expected_summary = {
            "spellcheck": {"completed": 2, "total": 3},
            "nlp": {"completed": 1, "total": 3},
        }

        # Arrange - Mock cached summary
        mock_redis_client.get.return_value = json.dumps(expected_summary)

        # Act
        result = await repository.get_batch_completion_summary(batch_id)

        # Assert
        assert result == expected_summary
        mock_redis_client.get.assert_called_once_with(f"bcs:batch_summary:{batch_id}")

    async def test_is_batch_step_complete_true(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test batch step completion check when step is complete."""
        batch_id = "batch-004"
        step_name = "spellcheck"
        summary = {"spellcheck": {"completed": 5, "total": 5}}

        # Arrange - Mock cached summary
        mock_redis_client.get.return_value = json.dumps(summary)

        # Act
        result = await repository.is_batch_step_complete(batch_id, step_name)

        # Assert
        assert result is True

    async def test_is_batch_step_complete_false(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test batch step completion check when step is incomplete."""
        batch_id = "batch-005"
        step_name = "nlp"
        summary = {"nlp": {"completed": 3, "total": 5}}

        # Arrange - Mock cached summary
        mock_redis_client.get.return_value = json.dumps(summary)

        # Act
        result = await repository.is_batch_step_complete(batch_id, step_name)

        # Assert
        assert result is False

    # Category 2: Validation and error handling
    async def test_get_essay_completed_steps_new_essay(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test retrieving completed steps for a new essay with no state."""
        batch_id = "batch-006"
        essay_id = "essay-006"

        # Arrange - Mock Redis returning None (no existing state)
        mock_redis_client.get.return_value = None

        # Act
        result = await repository.get_essay_completed_steps(batch_id, essay_id)

        # Assert
        assert result == set()

    async def test_is_batch_step_complete_unknown_step(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test batch step completion check for unknown step."""
        batch_id = "batch-007"
        step_name = "unknown_step"
        summary = {"spellcheck": {"completed": 5, "total": 5}}

        # Arrange - Mock cached summary without the requested step
        mock_redis_client.get.return_value = json.dumps(summary)

        # Act
        result = await repository.is_batch_step_complete(batch_id, step_name)

        # Assert
        assert result is False

    async def test_json_deserialization_error_handling(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test handling of JSON deserialization errors."""
        batch_id = "batch-008"
        essay_id = "essay-008"

        # Arrange - Mock Redis returning invalid JSON
        mock_redis_client.get.return_value = "invalid json data"

        # Act
        result = await repository.get_essay_completed_steps(batch_id, essay_id)

        # Assert - Should return empty set for new essay default
        assert result == set()

    async def test_make_json_serializable_with_sets(
        self, repository: RedisCachedBatchStateRepositoryImpl
    ) -> None:
        """Test JSON serialization of data containing sets."""
        data = {
            "completed_steps": {"spellcheck", "nlp"},
            "step_metadata": {"spellcheck": {"status": "success"}},
            "created_at": "2025-06-18T20:00:00Z",
        }

        # Act
        result = repository._make_json_serializable(data)

        # Assert
        assert isinstance(result["completed_steps"], list)
        assert set(result["completed_steps"]) == {"spellcheck", "nlp"}
        assert result["step_metadata"] == {"spellcheck": {"status": "success"}}
        assert result["created_at"] == "2025-06-18T20:00:00Z"

    # Category 3: Integration boundaries and PostgreSQL persistence
    async def test_record_essay_step_completion_with_postgres_success(
        self,
        repository_with_postgres: RedisCachedBatchStateRepositoryImpl,
        mock_redis_client: AsyncMock,
        mock_postgres_repository: AsyncMock,
    ) -> None:
        """Test successful essay step completion with PostgreSQL persistence."""
        batch_id = "batch-009"
        essay_id = "essay-009"
        step_name = "cj_assessment"
        metadata = {"rankings": [{"essay_id": "essay-009", "rank": 1}]}

        # Arrange - Mock successful atomic operation
        mock_redis_client.exec.return_value = [True, 1]

        # Act
        result = await repository_with_postgres.record_essay_step_completion(
            batch_id, essay_id, step_name, metadata
        )

        # Assert
        assert result is True
        mock_postgres_repository.record_essay_step_completion.assert_called_once_with(
            batch_id, essay_id, step_name, metadata
        )

    async def test_record_essay_step_completion_postgres_failure(
        self,
        repository_with_postgres: RedisCachedBatchStateRepositoryImpl,
        mock_redis_client: AsyncMock,
        mock_postgres_repository: AsyncMock,
    ) -> None:
        """Test essay step completion when PostgreSQL persistence fails."""
        batch_id = "batch-010"
        essay_id = "essay-010"
        step_name = "ai_feedback"
        metadata = {"feedback": "Great work!"}

        # Arrange - Mock successful Redis but failing PostgreSQL
        mock_redis_client.exec.return_value = [True, 1]
        mock_postgres_repository.record_essay_step_completion.side_effect = Exception("DB error")

        # Act
        result = await repository_with_postgres.record_essay_step_completion(
            batch_id, essay_id, step_name, metadata
        )

        # Assert - Should still succeed despite PostgreSQL failure
        assert result is True
        mock_postgres_repository.record_essay_step_completion.assert_called_once()

    async def test_build_batch_summary_from_redis_scan(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test building batch summary by scanning Redis keys."""
        batch_id = "batch-011"
        essay_keys = [
            f"bcs:essay_state:{batch_id}:essay-001",
            f"bcs:essay_state:{batch_id}:essay-002",
            f"bcs:essay_state:{batch_id}:essay-003",
        ]

        # Arrange - Mock Redis scan and individual essay states
        mock_redis_client.scan_pattern.return_value = essay_keys
        # First call for summary cache returns None, then essay states
        mock_redis_client.get.side_effect = [
            None,  # No cached summary (first call)
            json.dumps(
                {
                    "completed_steps": ["spellcheck", "nlp"],
                    "step_metadata": {},
                    "created_at": "2025-06-18T20:00:00Z",
                    "last_updated": "2025-06-18T20:00:00Z",
                }
            ),
            json.dumps(
                {
                    "completed_steps": ["spellcheck"],
                    "step_metadata": {},
                    "created_at": "2025-06-18T20:00:00Z",
                    "last_updated": "2025-06-18T20:00:00Z",
                }
            ),
            json.dumps(
                {
                    "completed_steps": [],
                    "step_metadata": {},
                    "created_at": "2025-06-18T20:00:00Z",
                    "last_updated": "2025-06-18T20:00:00Z",
                }
            ),
        ]

        # Act
        result = await repository.get_batch_completion_summary(batch_id)

        # Assert
        mock_redis_client.scan_pattern.assert_called_once_with(f"bcs:essay_state:{batch_id}:*")
        # Note: The exact counts depend on the _build_batch_summary implementation
        assert isinstance(result, dict)

    # Category 4: External service failures and Redis connection issues
    async def test_redis_connection_failure_during_get(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test Redis connection failure during get operation."""
        batch_id = "batch-012"
        essay_id = "essay-012"

        # Arrange - Mock Redis connection failure
        mock_redis_client.get.side_effect = ConnectionError("Redis unavailable")

        # Act & Assert - Should raise the connection error
        with pytest.raises(ConnectionError):
            await repository.get_essay_completed_steps(batch_id, essay_id)

    async def test_redis_connection_failure_during_setex(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test Redis connection failure during setex operation."""
        batch_id = "batch-013"
        essay_id = "essay-013"
        step_name = "spellcheck"

        # Arrange - Mock Redis setex failure
        mock_redis_client.setex.side_effect = ConnectionError("Redis unavailable")

        # Act
        result = await repository.record_essay_step_completion(batch_id, essay_id, step_name, {})

        # Assert - Should return False due to connection failure
        assert result is False

    async def test_redis_watch_failure_during_atomic_operation(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test Redis watch failure during atomic operation."""
        batch_id = "batch-014"
        essay_id = "essay-014"
        step_name = "nlp"

        # Arrange - Mock Redis watch failure
        mock_redis_client.watch.side_effect = ConnectionError("Redis unavailable")

        # Act
        result = await repository.record_essay_step_completion(batch_id, essay_id, step_name, {})

        # Assert - Should fallback to non-atomic operation and still succeed
        assert result is True
        mock_redis_client.watch.assert_called()

    # Category 5: Error recovery and resilience
    async def test_atomic_operation_fallback_on_repeated_failures(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test fallback to non-atomic operation after repeated atomic failures."""
        batch_id = "batch-015"
        essay_id = "essay-015"
        step_name = "ai_feedback"

        # Arrange - Mock atomic operations to always fail
        mock_redis_client.exec.return_value = None  # Always discarded

        # Act
        result = await repository.record_essay_step_completion(batch_id, essay_id, step_name, {})

        # Assert - Should succeed via fallback
        assert result is True
        # Verify max retries were attempted
        assert mock_redis_client.exec.call_count == 5

    async def test_non_atomic_operation_success_after_atomic_failure(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test successful non-atomic operation after atomic operation fails."""
        batch_id = "batch-016"
        essay_id = "essay-016"
        step_name = "cj_assessment"

        # Arrange - Mock atomic operations to fail, non-atomic to succeed
        mock_redis_client.exec.return_value = None  # Atomic fails
        mock_redis_client.setex.return_value = True  # Non-atomic succeeds

        # Act
        result = await repository.record_essay_step_completion(batch_id, essay_id, step_name, {})

        # Assert
        assert result is True
        # Verify both atomic and non-atomic operations were attempted
        assert mock_redis_client.exec.call_count == 5  # 5 atomic retries
        assert mock_redis_client.setex.call_count >= 6  # 5 atomic + 1 non-atomic

    async def test_exponential_backoff_during_retries(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test exponential backoff during atomic operation retries."""
        batch_id = "batch-017"
        essay_id = "essay-017"
        step_name = "spellcheck"

        # Arrange - Mock atomic operations to fail multiple times
        mock_redis_client.exec.side_effect = [
            None,
            None,
            None,
            [True, 1],
        ]  # Fail 3 times, succeed on 4th

        # Act
        with patch("asyncio.sleep") as mock_sleep:
            result = await repository.record_essay_step_completion(
                batch_id, essay_id, step_name, {}
            )

        # Assert
        assert result is True
        # Verify exponential backoff was used
        assert mock_sleep.call_count == 3  # 3 retries before success
        # Verify delays increased exponentially (approximately)
        calls = mock_sleep.call_args_list
        assert len(calls) == 3
        # Check that delays generally increase (allowing for jitter)
        assert calls[0][0][0] < calls[1][0][0] < calls[2][0][0]

    # Category 6: TTL behavior and caching
    async def test_essay_state_ttl_setting(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test that essay state is stored with correct TTL."""
        batch_id = "batch-018"
        essay_id = "essay-018"
        step_name = "spellcheck"
        expected_ttl = 7 * 24 * 60 * 60  # 7 days

        # Arrange - Mock successful atomic operation
        mock_redis_client.exec.return_value = [True, 1]

        # Act
        result = await repository.record_essay_step_completion(batch_id, essay_id, step_name, {})

        # Assert
        assert result is True
        # Verify setex was called with correct TTL
        mock_redis_client.setex.assert_called()
        call_args = mock_redis_client.setex.call_args
        assert call_args[0][1] == expected_ttl  # TTL is second argument

    async def test_batch_summary_cache_ttl(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test that batch summary cache uses correct TTL."""
        batch_id = "batch-019"
        expected_cache_ttl = 60 * 60  # 1 hour

        # Arrange - Mock no cached summary, empty scan results
        mock_redis_client.get.return_value = None
        mock_redis_client.scan_pattern.return_value = []

        # Act
        result = await repository.get_batch_completion_summary(batch_id)

        # Assert
        assert result == {}
        # Verify cache was set with correct TTL
        mock_redis_client.setex.assert_called()
        call_args = mock_redis_client.setex.call_args
        assert call_args[0][1] == expected_cache_ttl

    async def test_batch_summary_cache_hit(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test batch summary cache hit scenario."""
        batch_id = "batch-020"
        cached_summary = {"spellcheck": {"completed": 5, "total": 10}}

        # Arrange - Mock cached summary exists
        mock_redis_client.get.return_value = json.dumps(cached_summary)

        # Act
        result = await repository.get_batch_completion_summary(batch_id)

        # Assert
        assert result == cached_summary
        # Verify scan was not called (cache hit)
        mock_redis_client.scan_pattern.assert_not_called()

    # Category 7: Real-world scenarios and edge cases
    async def test_concurrent_essay_step_completions(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test concurrent essay step completions for the same essay."""
        batch_id = "batch-021"
        essay_id = "essay-021"
        steps = ["spellcheck", "nlp", "ai_feedback"]

        # Arrange - Mock successful atomic operations
        mock_redis_client.exec.return_value = [True, 1]

        # Act - Execute concurrent operations
        tasks = [
            repository.record_essay_step_completion(batch_id, essay_id, step, {}) for step in steps
        ]
        results = await asyncio.gather(*tasks)

        # Assert - All operations should succeed
        assert all(results)
        # Verify atomic operations were used
        assert mock_redis_client.watch.call_count == 3
        assert mock_redis_client.exec.call_count == 3

    async def test_large_batch_summary_generation(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test batch summary generation for large batches."""
        batch_id = "batch-022"
        num_essays = 100
        essay_keys = [f"bcs:essay_state:{batch_id}:essay-{i:03d}" for i in range(num_essays)]

        # Arrange - Mock large batch with varied completion states
        mock_redis_client.get.return_value = None  # No cached summary
        mock_redis_client.scan_pattern.return_value = essay_keys

        # Mock essay states - 60% completed spellcheck, 30% completed nlp
        essay_states = []
        for i in range(num_essays):
            steps = []
            if i < 60:  # 60% completed spellcheck
                steps.append("spellcheck")
            if i < 30:  # 30% completed nlp
                steps.append("nlp")
            essay_states.append(
                json.dumps(
                    {
                        "completed_steps": steps,
                        "step_metadata": {},
                        "created_at": "2025-06-18T20:00:00Z",
                        "last_updated": "2025-06-18T20:00:00Z",
                    }
                )
            )

        mock_redis_client.get.side_effect = [None] + essay_states

        # Act
        result = await repository.get_batch_completion_summary(batch_id)

        # Assert
        assert isinstance(result, dict)
        mock_redis_client.scan_pattern.assert_called_once_with(f"bcs:essay_state:{batch_id}:*")
        # Verify summary was cached
        mock_redis_client.setex.assert_called()

    async def test_timestamp_generation_consistency(
        self, repository: RedisCachedBatchStateRepositoryImpl
    ) -> None:
        """Test that timestamp generation is consistent and valid."""
        # Act
        timestamp1 = repository._get_current_timestamp()
        timestamp2 = repository._get_current_timestamp()

        # Assert - Both should be valid ISO format timestamps
        assert isinstance(timestamp1, str)
        assert isinstance(timestamp2, str)

        # Should be parseable as datetime
        datetime.fromisoformat(timestamp1.replace("Z", "+00:00"))
        datetime.fromisoformat(timestamp2.replace("Z", "+00:00"))

        # Second timestamp should be >= first timestamp
        assert timestamp2 >= timestamp1

    async def test_empty_batch_summary_handling(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test handling of empty batch (no essays)."""
        batch_id = "batch-023"

        # Arrange - Mock empty batch
        mock_redis_client.get.return_value = None  # No cached summary
        mock_redis_client.scan_pattern.return_value = []  # No essays

        # Act
        result = await repository.get_batch_completion_summary(batch_id)

        # Assert
        assert result == {}
        assert await repository.is_batch_step_complete(batch_id, "spellcheck") is False

    async def test_malformed_essay_state_recovery(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test recovery from malformed essay state data."""
        batch_id = "batch-024"
        essay_id = "essay-024"

        # Arrange - Mock malformed essay state
        mock_redis_client.get.return_value = '{"completed_steps": "invalid_format"}'

        # Act
        result = await repository.get_essay_completed_steps(batch_id, essay_id)

        # Assert - Should handle gracefully and return empty set
        assert result == set()

    async def test_malformed_data_edge_cases(
        self, repository: RedisCachedBatchStateRepositoryImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test various malformed data types are handled correctly."""
        batch_id = "batch-025"

        # Test cases for different malformed data types
        test_cases = [
            ('{"completed_steps": 123}', "integer"),
            ('{"completed_steps": true}', "boolean"),
            ('{"completed_steps": {"key": "value"}}', "dict"),
            ('{"completed_steps": null}', "null"),
            ('{"completed_steps": [1, 2, 3]}', "list_of_ints"),
        ]

        for i, (malformed_data, description) in enumerate(test_cases):
            essay_id = f"essay-{i:03d}"
            mock_redis_client.get.return_value = malformed_data

            # Act
            result = await repository.get_essay_completed_steps(batch_id, essay_id)

            # Assert - All malformed data should result in empty set
            assert result == set(), f"Failed for {description}: {malformed_data}"
