"""
Unit tests for queue manager remove behavior.

Tests that ResilientQueueManager.remove() actually calls the underlying
delete methods to prevent queue clogging.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.resilient_queue_manager_impl import (
    ResilientQueueManagerImpl,
)


class TestResilientQueueManagerRemove:
    """Test ResilientQueueManager.remove() calls underlying delete methods."""

    @pytest.fixture
    def mock_redis_queue(self) -> AsyncMock:
        """Mock Redis queue repository."""
        mock = AsyncMock()
        mock.delete = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def mock_local_queue(self) -> AsyncMock:
        """Mock local queue manager."""
        mock = AsyncMock()
        mock.delete = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def settings(self) -> Settings:
        """Test settings."""
        return Settings()

    @pytest.fixture
    def queue_manager(
        self, mock_redis_queue: AsyncMock, mock_local_queue: AsyncMock, settings: Settings
    ) -> ResilientQueueManagerImpl:
        """ResilientQueueManager with mocked dependencies."""
        return ResilientQueueManagerImpl(
            redis_queue=mock_redis_queue, local_queue=mock_local_queue, settings=settings
        )

    @pytest.mark.asyncio
    async def test_remove_calls_redis_delete_when_redis_healthy(
        self, queue_manager: ResilientQueueManagerImpl, mock_redis_queue: AsyncMock
    ) -> None:
        """Test that remove() calls redis_queue.delete() when Redis is healthy."""
        # Ensure Redis is marked as healthy
        queue_manager._redis_healthy = True

        queue_id = uuid4()
        result = await queue_manager.remove(queue_id)

        # Verify the result and method call
        assert result is True
        mock_redis_queue.delete.assert_called_once_with(queue_id)

    @pytest.mark.asyncio
    async def test_remove_calls_local_delete_when_redis_unhealthy(
        self,
        queue_manager: ResilientQueueManagerImpl,
        mock_local_queue: AsyncMock,
        mock_redis_queue: AsyncMock,
    ) -> None:
        """Test that remove() calls local_queue.delete() when Redis is unhealthy."""
        # Simulate Redis being unhealthy
        queue_manager._redis_healthy = False

        queue_id = uuid4()
        result = await queue_manager.remove(queue_id)

        # Verify Redis delete was not called
        mock_redis_queue.delete.assert_not_called()

        # Verify local delete was called
        mock_local_queue.delete.assert_called_once_with(queue_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_remove_tries_both_when_redis_fails(
        self,
        queue_manager: ResilientQueueManagerImpl,
        mock_redis_queue: AsyncMock,
        mock_local_queue: AsyncMock,
    ) -> None:
        """Test that remove() tries local when Redis delete fails."""
        # Redis is healthy but delete fails
        queue_manager._redis_healthy = True
        mock_redis_queue.delete.return_value = False  # Redis delete fails

        queue_id = uuid4()
        result = await queue_manager.remove(queue_id)

        # Verify both were called
        mock_redis_queue.delete.assert_called_once_with(queue_id)
        mock_local_queue.delete.assert_called_once_with(queue_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_remove_cleans_up_migration_tracking(
        self, queue_manager: ResilientQueueManagerImpl, mock_local_queue: AsyncMock
    ) -> None:
        """Test that remove() cleans up migration tracking."""
        queue_id = uuid4()

        # Add to migration tracking
        queue_manager._migrated_to_local.add(queue_id)
        assert queue_id in queue_manager._migrated_to_local

        # Remove the request
        await queue_manager.remove(queue_id)

        # Verify migration tracking was cleaned up
        assert queue_id not in queue_manager._migrated_to_local

    @pytest.mark.asyncio
    async def test_cleanup_expired_records_expiry_counter_for_total_cleaned(
        self,
        queue_manager: ResilientQueueManagerImpl,
        mock_redis_queue: AsyncMock,
        mock_local_queue: AsyncMock,
    ) -> None:
        """Cleanup should increment llm_queue_expiry_total for all cleaned items."""

        queue_manager.queue_metrics = {"llm_queue_expiry_total": Mock()}
        expiry_counter = queue_manager.queue_metrics["llm_queue_expiry_total"]
        expiry_counter.labels.return_value = Mock()

        mock_redis_queue.cleanup_expired = AsyncMock(return_value=2)
        mock_local_queue.cleanup_expired = AsyncMock(return_value=3)
        mock_redis_queue.get_all_queued = AsyncMock(return_value=[])
        mock_local_queue.get_all_queued = AsyncMock(return_value=[])

        queue_manager._redis_healthy = True

        total_cleaned = await queue_manager.cleanup_expired()

        assert total_cleaned == 5

        expiry_counter.labels.assert_called_once_with(
            provider="unknown",
            queue_processing_mode=queue_manager.settings.QUEUE_PROCESSING_MODE.value,
            expiry_reason="cleanup",
        )
        expiry_counter.labels.return_value.inc.assert_called_once_with(5)

    @pytest.mark.asyncio
    async def test_cleanup_expired_does_not_record_metrics_when_zero_cleaned(
        self,
        queue_manager: ResilientQueueManagerImpl,
        mock_redis_queue: AsyncMock,
        mock_local_queue: AsyncMock,
    ) -> None:
        """Cleanup should not touch metrics when no expired items are removed."""

        queue_manager.queue_metrics = {"llm_queue_expiry_total": Mock()}
        expiry_counter = queue_manager.queue_metrics["llm_queue_expiry_total"]
        expiry_counter.labels.return_value = Mock()

        mock_redis_queue.cleanup_expired = AsyncMock(return_value=0)
        mock_local_queue.cleanup_expired = AsyncMock(return_value=0)
        mock_redis_queue.get_all_queued = AsyncMock(return_value=[])
        mock_local_queue.get_all_queued = AsyncMock(return_value=[])

        queue_manager._redis_healthy = True

        total_cleaned = await queue_manager.cleanup_expired()

        assert total_cleaned == 0
        expiry_counter.labels.assert_not_called()
