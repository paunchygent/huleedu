"""
Test suite for MockBatchStateRepositoryImpl.

Validates atomic operation simulation, TTL behavior, and protocol compliance.
"""

from __future__ import annotations

import pytest

from services.batch_conductor_service.implementations.mock_batch_state_repository import (
    MockBatchStateRepositoryImpl,
)


class TestMockBatchStateRepository:
    """Test mock batch state repository implementation."""

    @pytest.fixture
    def mock_repository(self) -> MockBatchStateRepositoryImpl:
        """Create a fresh mock repository for each test."""
        return MockBatchStateRepositoryImpl()

    @pytest.mark.asyncio
    async def test_atomic_operation_simulation(
        self, mock_repository: MockBatchStateRepositoryImpl
    ) -> None:
        """Test that mock repository simulates Redis atomic behavior."""
        batch_id = "test-batch-001"
        essay_id = "essay-001"
        step_name = "spellcheck"

        # First completion should succeed
        result = await mock_repository.record_essay_step_completion(batch_id, essay_id, step_name)
        assert result is True

        # Idempotent - second completion should also succeed but not duplicate
        result = await mock_repository.record_essay_step_completion(batch_id, essay_id, step_name)
        assert result is True

        # Verify the step is recorded exactly once
        completed_steps = await mock_repository.get_essay_completed_steps(batch_id, essay_id)
        assert step_name in completed_steps
        assert len(completed_steps) == 1

    @pytest.mark.asyncio
    async def test_protocol_compliance(
        self, mock_repository: MockBatchStateRepositoryImpl
    ) -> None:
        """Ensure mock implements same interface as Redis repository."""
        batch_id = "test-batch-002"
        essay_id = "essay-002"
        step_name = "nlp"

        # Test record_essay_step_completion
        result = await mock_repository.record_essay_step_completion(
            batch_id, essay_id, step_name, {"test": "metadata"}
        )
        assert result is True

        # Test get_essay_completed_steps
        completed_steps = await mock_repository.get_essay_completed_steps(batch_id, essay_id)
        assert isinstance(completed_steps, set)
        assert step_name in completed_steps

        # Test get_batch_completion_summary
        summary = await mock_repository.get_batch_completion_summary(batch_id)
        assert isinstance(summary, dict)
        assert step_name in summary
        assert "completed" in summary[step_name]
        assert "total" in summary[step_name]
        assert summary[step_name]["completed"] == 1
        assert summary[step_name]["total"] == 1

        # Test is_batch_step_complete
        is_complete = await mock_repository.is_batch_step_complete(batch_id, step_name)
        assert is_complete is True

        # Test with incomplete step
        incomplete_step = "ai_feedback"
        is_complete = await mock_repository.is_batch_step_complete(batch_id, incomplete_step)
        assert is_complete is False

    @pytest.mark.asyncio
    async def test_ttl_simulation(
        self, mock_repository: MockBatchStateRepositoryImpl
    ) -> None:
        """Test TTL expiration simulation."""
        batch_id = "test-batch-003"
        essay_id = "essay-003"
        step_name = "spellcheck"

        # Record a step
        await mock_repository.record_essay_step_completion(batch_id, essay_id, step_name)

        # Verify it's there
        completed_steps = await mock_repository.get_essay_completed_steps(batch_id, essay_id)
        assert step_name in completed_steps

        # Manually expire the entry (simulating TTL)
        essay_key = f"bcs:essay_state:{batch_id}:{essay_id}"
        expiry_time = mock_repository.ttl_expiry[essay_key].replace(year=2020)
        mock_repository.ttl_expiry[essay_key] = expiry_time

        # Should return empty set after expiry
        completed_steps = await mock_repository.get_essay_completed_steps(batch_id, essay_id)
        assert len(completed_steps) == 0

    @pytest.mark.asyncio
    async def test_batch_summary_with_multiple_essays(
        self, mock_repository: MockBatchStateRepositoryImpl
    ) -> None:
        """Test batch summary calculation with multiple essays."""
        batch_id = "test-batch-004"
        step_name = "spellcheck"

        # Record completion for multiple essays
        essay_ids = ["essay-001", "essay-002", "essay-003"]
        for essay_id in essay_ids:
            await mock_repository.record_essay_step_completion(batch_id, essay_id, step_name)

        # Only complete step for first two essays on a different step
        different_step = "nlp"
        for essay_id in essay_ids[:2]:
            await mock_repository.record_essay_step_completion(batch_id, essay_id, different_step)

        # Get batch summary
        summary = await mock_repository.get_batch_completion_summary(batch_id)

        # Verify spellcheck is complete for all 3 essays
        assert summary[step_name]["completed"] == 3
        assert summary[step_name]["total"] == 3

        # Verify nlp is complete for only 2 essays
        assert summary[different_step]["completed"] == 2
        assert summary[different_step]["total"] == 3

    @pytest.mark.asyncio
    async def test_cleanup_expired_data(
        self, mock_repository: MockBatchStateRepositoryImpl
    ) -> None:
        """Test cleanup of expired data."""
        batch_id = "test-batch-005"
        essay_id = "essay-005"
        step_name = "spellcheck"

        # Record a step
        await mock_repository.record_essay_step_completion(batch_id, essay_id, step_name)

        # Manually expire the entry
        essay_key = f"bcs:essay_state:{batch_id}:{essay_id}"
        expiry_time = mock_repository.ttl_expiry[essay_key].replace(year=2020)
        mock_repository.ttl_expiry[essay_key] = expiry_time

        # Run cleanup
        cleaned_count = await mock_repository.cleanup_expired_data()
        assert cleaned_count == 1

        # Verify data is cleaned up
        assert essay_key not in mock_repository.essay_states
        assert essay_key not in mock_repository.ttl_expiry
