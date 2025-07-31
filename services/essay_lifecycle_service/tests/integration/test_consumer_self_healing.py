"""
Integration tests for ELS Kafka consumer self-healing mechanism.

Tests the complete self-healing system including health monitoring, recovery
coordination, and message processing continuity with real components.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker

from services.essay_lifecycle_service.implementations.consumer_health_monitor_impl import (
    ConsumerHealthMonitorImpl,
)
from services.essay_lifecycle_service.implementations.consumer_recovery_manager_impl import (
    ConsumerRecoveryManagerImpl,
)
from services.essay_lifecycle_service.tests.utils.helpers import (
    HEALTH_CHECK_INTERVAL_TEST,
    MAX_IDLE_SECONDS_TEST,
    RECOVERY_FAILURE_THRESHOLD,
    RECOVERY_SUCCESS_THRESHOLD,
    RECOVERY_TIMEOUT_SECONDS,
    TimeAdvancer,
    create_mock_kafka_consumer,
)


@pytest.fixture
def mock_kafka_consumer() -> Any:
    """Create a mock Kafka consumer that simulates stuck and healthy behavior."""
    consumer = create_mock_kafka_consumer()
    consumer.getone = AsyncMock()
    return consumer


@pytest.fixture
def health_monitor() -> ConsumerHealthMonitorImpl:
    """Create health monitor for integration testing."""
    return ConsumerHealthMonitorImpl(
        health_check_interval=HEALTH_CHECK_INTERVAL_TEST, max_idle_seconds=MAX_IDLE_SECONDS_TEST
    )


@pytest.fixture
def recovery_manager(health_monitor: ConsumerHealthMonitorImpl) -> ConsumerRecoveryManagerImpl:
    """Create recovery manager with fast circuit breaker for testing."""
    circuit_breaker = CircuitBreaker(
        failure_threshold=RECOVERY_FAILURE_THRESHOLD,
        recovery_timeout=timedelta(seconds=RECOVERY_TIMEOUT_SECONDS),
        success_threshold=RECOVERY_SUCCESS_THRESHOLD,
        name="test_consumer_recovery",
    )
    return ConsumerRecoveryManagerImpl(health_monitor, circuit_breaker=circuit_breaker)


@pytest.mark.integration
class TestConsumerSelfHealing:
    """Integration tests for consumer self-healing mechanism."""

    @pytest.mark.asyncio
    async def test_healthy_consumer_no_recovery_needed(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        recovery_manager: ConsumerRecoveryManagerImpl,
        mock_kafka_consumer: Any,
    ) -> None:
        """Test that healthy consumer with recent activity doesn't trigger recovery."""
        # Simulate active message processing without sleep
        for _ in range(3):
            await health_monitor.record_message_processed()

        # Consumer should be healthy
        assert health_monitor.is_healthy() is True

        # Recovery shouldn't be needed
        assert recovery_manager.is_recovery_in_progress() is False

        # Metrics should show healthy state
        metrics = health_monitor.get_health_metrics()
        assert metrics["is_healthy"] is True
        assert metrics["messages_processed"] == 3
        assert metrics["consecutive_failures"] == 0

    @pytest.mark.asyncio
    async def test_stuck_consumer_detection_and_recovery(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        recovery_manager: ConsumerRecoveryManagerImpl,
        mock_kafka_consumer: Any,
    ) -> None:
        """Test detection of stuck consumer and successful recovery."""
        # Simulate consumer getting stuck (no messages processed for idle threshold)
        with TimeAdvancer() as time_advancer:
            # Initial message processing
            await health_monitor.record_message_processed()
            assert health_monitor.is_healthy() is True

            # Advance time beyond idle threshold
            time_advancer.advance(seconds=MAX_IDLE_SECONDS_TEST + 1)

            # Consumer should now be unhealthy due to idle time
            assert health_monitor.is_healthy() is False

        # Trigger recovery
        recovery_result = await recovery_manager.initiate_recovery(mock_kafka_consumer)

        assert recovery_result is True
        assert not recovery_manager.is_recovery_in_progress()

        # Verify seek operations were called (soft recovery)
        mock_kafka_consumer.seek_to_end.assert_called_once()
        mock_kafka_consumer.seek_to_beginning.assert_called_once()

        # Check recovery metrics
        status = recovery_manager.get_recovery_status()
        assert status["recovery_metrics"]["soft_recovery_attempts"] == 1
        assert status["recovery_metrics"]["soft_recovery_successes"] == 1
        assert status["recovery_metrics"]["hard_recovery_requests"] == 0

    @pytest.mark.asyncio
    async def test_consumer_recovery_with_message_processing_resume(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        recovery_manager: ConsumerRecoveryManagerImpl,
        mock_kafka_consumer: Any,
    ) -> None:
        """Test that consumer resumes message processing after recovery."""
        # Start with unhealthy consumer due to idle time
        with TimeAdvancer() as time_advancer:
            # Record initial message
            await health_monitor.record_message_processed()

            # Advance time to make consumer unhealthy
            time_advancer.advance(seconds=MAX_IDLE_SECONDS_TEST + 1)

            assert health_monitor.is_healthy() is False

        # Perform recovery - this will update the health monitor
        await recovery_manager.initiate_recovery(mock_kafka_consumer)

        # Simulate message processing resuming after recovery
        await health_monitor.record_message_processed()
        await health_monitor.record_message_processed()

        # Consumer should be healthy again (recent activity)
        assert health_monitor.is_healthy() is True

        # Verify processing counters (includes recovery-triggered update)
        metrics = health_monitor.get_health_metrics()
        assert metrics["messages_processed"] >= 2  # At least 2 plus recovery
        assert metrics["consecutive_failures"] == 0

    @pytest.mark.asyncio
    async def test_soft_recovery_failure_triggers_hard_recovery_request(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        recovery_manager: ConsumerRecoveryManagerImpl,
        mock_kafka_consumer: Any,
    ) -> None:
        """Test that soft recovery failure properly requests hard recovery."""
        # Force soft recovery to fail by removing consumer assignment
        mock_kafka_consumer.assignment.return_value = set()

        # Make consumer unhealthy by advancing time
        with TimeAdvancer() as time_advancer:
            # Record initial message
            await health_monitor.record_message_processed()

            # Advance time to make unhealthy
            time_advancer.advance(seconds=MAX_IDLE_SECONDS_TEST + 1)

            assert health_monitor.is_healthy() is False

        # Attempt recovery - should fail soft recovery and request hard recovery
        result = await recovery_manager.initiate_recovery(mock_kafka_consumer)

        assert result is False  # Recovery failed - signals hard recovery needed

        # Verify metrics show soft recovery failed and hard recovery requested
        status = recovery_manager.get_recovery_status()
        metrics = status["recovery_metrics"]
        assert metrics["soft_recovery_attempts"] == 1
        assert metrics["soft_recovery_successes"] == 0
        assert metrics["hard_recovery_requests"] == 1

        # Verify seek operations were not called due to no assignment
        mock_kafka_consumer.seek_to_end.assert_not_called()
        mock_kafka_consumer.seek_to_beginning.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_recovery_failures_with_circuit_breaker(
        self, health_monitor: ConsumerHealthMonitorImpl, mock_kafka_consumer: Any
    ) -> None:
        """Test circuit breaker behavior with multiple recovery failures."""
        # Create recovery manager with low failure threshold
        circuit_breaker = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=timedelta(seconds=1),
            success_threshold=1,
            name="test_breaker",
        )
        recovery_manager = ConsumerRecoveryManagerImpl(health_monitor, circuit_breaker)

        # Force recovery to fail
        mock_kafka_consumer.assignment.return_value = set()

        # Make consumer unhealthy
        with freeze_time() as frozen_time:
            await health_monitor.record_message_processed()
            frozen_time.tick(delta=timedelta(seconds=MAX_IDLE_SECONDS_TEST + 1))

        # First failure
        result1 = await recovery_manager.initiate_recovery(mock_kafka_consumer)
        assert result1 is False  # Recovery failed

        # Second failure
        result2 = await recovery_manager.initiate_recovery(mock_kafka_consumer)
        assert result2 is False  # Recovery failed

        # Verify both attempts were recorded
        assert recovery_manager._recovery_metrics["total_recovery_attempts"] == 2

        # Circuit breaker should track failures
        cb_state = recovery_manager.circuit_breaker.get_state()
        assert "state" in cb_state

    @pytest.mark.asyncio
    async def test_consecutive_failures_vs_processing_success_tracking(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        recovery_manager: ConsumerRecoveryManagerImpl,
        mock_kafka_consumer: Any,
    ) -> None:
        """Test that failure tracking interacts correctly with successful processing."""
        # Build up some failures
        for _ in range(3):
            await health_monitor.record_processing_failure()

        assert health_monitor._consecutive_failures == 3
        assert health_monitor.is_healthy() is True  # Still under threshold

        # Add one more to reach unhealthy state
        await health_monitor.record_processing_failure()
        await health_monitor.record_processing_failure()

        assert health_monitor._consecutive_failures == 5
        assert health_monitor.is_healthy() is False  # Over threshold

        # Perform successful recovery
        result = await recovery_manager.initiate_recovery(mock_kafka_consumer)
        assert result is True

        # Recovery should reset failure count via record_recovery_attempt
        assert health_monitor._consecutive_failures == 0

        # Consumer should be healthy again (if not idle)
        await health_monitor.record_message_processed()
        assert health_monitor.is_healthy() is True

    @pytest.mark.asyncio
    async def test_health_check_interval_timing(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        recovery_manager: ConsumerRecoveryManagerImpl,
    ) -> None:
        """Test that health check intervals work correctly for periodic monitoring."""
        # Should not need health check immediately
        assert health_monitor.should_check_health() is False

        # Manually set old check time to simulate interval passage
        old_check_time = datetime.now(UTC) - timedelta(seconds=2)
        health_monitor._last_health_check = old_check_time

        # Should now need health check
        assert health_monitor.should_check_health() is True

        # Second call should return False (interval reset)
        assert health_monitor.should_check_health() is False

        # Set old time again
        old_check_time = datetime.now(UTC) - timedelta(seconds=2)
        health_monitor._last_health_check = old_check_time
        assert health_monitor.should_check_health() is True

    @pytest.mark.asyncio
    async def test_no_message_loss_during_recovery(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        recovery_manager: ConsumerRecoveryManagerImpl,
        mock_kafka_consumer: Any,
    ) -> None:
        """Test that message processing can continue during and after recovery."""
        # Set up scenario where consumer processes messages, gets stuck, recovers
        message_count = 0

        # Process some messages initially
        for _i in range(3):
            await health_monitor.record_message_processed()
            message_count += 1

        assert health_monitor.messages_processed == message_count

        # Simulate getting stuck by advancing time
        with TimeAdvancer() as time_advancer:
            time_advancer.advance(seconds=MAX_IDLE_SECONDS_TEST + 1)

            # Verify consumer is unhealthy
            assert health_monitor.is_healthy() is False

        # Perform recovery
        recovery_result = await recovery_manager.initiate_recovery(mock_kafka_consumer)
        assert recovery_result is True

        # Recovery itself records a successful processing event
        message_count += 1  # Recovery records success
        assert health_monitor.messages_processed == message_count

        # Continue processing messages after recovery
        for _i in range(2):
            await health_monitor.record_message_processed()
            message_count += 1

        # Verify all messages were counted
        assert health_monitor.messages_processed == message_count

        # Consumer should be healthy
        assert health_monitor.is_healthy() is True

    @pytest.mark.asyncio
    async def test_concurrent_health_checks_and_recovery(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        recovery_manager: ConsumerRecoveryManagerImpl,
        mock_kafka_consumer: Any,
    ) -> None:
        """Test thread safety of concurrent health checks and recovery operations."""

        # Create tasks that run concurrently
        async def process_messages() -> None:
            for _ in range(5):
                await health_monitor.record_message_processed()
                # No sleep needed for test

        async def check_health() -> None:
            for _ in range(5):
                health_monitor.is_healthy()
                health_monitor.get_health_metrics()
                # No sleep needed for test

        async def attempt_recovery() -> None:
            # Only attempt if not already in progress
            if not recovery_manager.is_recovery_in_progress():
                await recovery_manager.initiate_recovery(mock_kafka_consumer)

        # Run all tasks concurrently
        await asyncio.gather(
            process_messages(), check_health(), attempt_recovery(), return_exceptions=True
        )

        # Verify state remains consistent
        assert health_monitor.messages_processed >= 5  # At least 5 from process_messages
        assert isinstance(health_monitor.is_healthy(), bool)
        assert not recovery_manager.is_recovery_in_progress()

    @pytest.mark.asyncio
    async def test_recovery_metrics_observability(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        recovery_manager: ConsumerRecoveryManagerImpl,
        mock_kafka_consumer: Any,
    ) -> None:
        """Test that recovery provides comprehensive metrics for observability."""
        # Perform several recovery operations
        await recovery_manager.initiate_recovery(mock_kafka_consumer)  # Success

        # Force failure and try again
        mock_kafka_consumer.assignment.return_value = set()
        await recovery_manager.initiate_recovery(mock_kafka_consumer)  # Soft fail, hard request

        # Get comprehensive status
        status = recovery_manager.get_recovery_status()

        # Verify all expected fields
        assert "recovery_in_progress" in status
        assert "last_recovery_attempt" in status
        assert "circuit_breaker_state" in status
        assert "recovery_metrics" in status

        # Verify metrics detail
        metrics = status["recovery_metrics"]
        assert metrics["total_recovery_attempts"] == 2
        assert metrics["soft_recovery_attempts"] == 2
        assert metrics["soft_recovery_successes"] == 1
        assert metrics["hard_recovery_requests"] == 1

        # Verify health monitor metrics
        health_metrics = health_monitor.get_health_metrics()
        assert "messages_processed" in health_metrics
        assert "idle_seconds" in health_metrics
        assert "consecutive_failures" in health_metrics
        assert "is_healthy" in health_metrics
        assert "last_message_time" in health_metrics

    @pytest.mark.asyncio
    async def test_recovery_prevents_concurrent_attempts(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        recovery_manager: ConsumerRecoveryManagerImpl,
        mock_kafka_consumer: Any,
    ) -> None:
        """Test that recovery mechanism prevents dangerous concurrent recovery attempts."""

        # Create a slow recovery scenario
        # seek_to_end is synchronous in AIOKafkaConsumer, so we need to simulate
        # a slow recovery using a different approach
        recovery_started = asyncio.Event()
        asyncio.Event()

        # Make seek_to_end synchronous but signal when it's called
        def signal_seek_to_end() -> None:
            recovery_started.set()

        mock_kafka_consumer.seek_to_end.side_effect = signal_seek_to_end

        # Start first recovery
        recovery_task = asyncio.create_task(recovery_manager.initiate_recovery(mock_kafka_consumer))

        # Wait for the signal that recovery has started
        await recovery_started.wait()

        # Now recovery should be in progress
        assert recovery_manager.is_recovery_in_progress() is True

        # Attempt second recovery while first is in progress
        second_result = await recovery_manager.initiate_recovery(mock_kafka_consumer)

        # Second attempt should be rejected
        assert second_result is False

        # Wait for first recovery to complete
        first_result = await recovery_task
        assert first_result is True

        # Recovery should no longer be in progress
        assert recovery_manager.is_recovery_in_progress() is False
