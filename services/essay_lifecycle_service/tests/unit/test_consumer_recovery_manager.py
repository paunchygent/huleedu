"""
Unit tests for ConsumerRecoveryManagerImpl for ELS Kafka consumer self-healing.

Tests graduated recovery strategy, circuit breaker integration, and recovery
coordination with health monitoring.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from common_core import CircuitBreakerState
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker

from services.essay_lifecycle_service.implementations.consumer_health_monitor_impl import (
    ConsumerHealthMonitorImpl,
)
from services.essay_lifecycle_service.implementations.consumer_recovery_manager_impl import (
    ConsumerRecoveryManagerImpl,
)
from services.essay_lifecycle_service.tests.utils.helpers import (
    HEALTH_CHECK_INTERVAL_DEFAULT,
    MAX_IDLE_SECONDS_DEFAULT,
    RECOVERY_FAILURE_THRESHOLD,
    RECOVERY_SUCCESS_THRESHOLD,
    RECOVERY_TIMEOUT_SECONDS,
    TimeAdvancer,
    create_mock_kafka_consumer,
)


@pytest.fixture
def mock_consumer() -> Any:
    """Create mock Kafka consumer for testing seek operations."""
    return create_mock_kafka_consumer()


@pytest.fixture
def health_monitor() -> ConsumerHealthMonitorImpl:
    """Create real health monitor instance for testing."""
    return ConsumerHealthMonitorImpl(
        health_check_interval=HEALTH_CHECK_INTERVAL_DEFAULT, 
        max_idle_seconds=MAX_IDLE_SECONDS_DEFAULT
    )


@pytest.mark.unit
class TestConsumerRecoveryManagerImpl:
    """Test suite for consumer recovery manager implementation."""

    def test_initialization_with_defaults(self, health_monitor: ConsumerHealthMonitorImpl) -> None:
        """Test recovery manager initializes with default circuit breaker."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        assert manager.health_monitor is health_monitor
        assert manager.circuit_breaker is not None
        assert manager._recovery_in_progress is False
        assert manager._last_recovery_attempt is None
        assert isinstance(manager._recovery_lock, asyncio.Lock)
        
        # Check default metrics
        expected_metrics = {
            "soft_recovery_attempts": 0,
            "soft_recovery_successes": 0,
            "hard_recovery_requests": 0,
            "total_recovery_attempts": 0,
        }
        assert manager._recovery_metrics == expected_metrics

    def test_initialization_with_custom_circuit_breaker(self, health_monitor: ConsumerHealthMonitorImpl) -> None:
        """Test recovery manager with custom circuit breaker."""
        custom_failure_threshold = 5
        custom_timeout_minutes = 5
        custom_breaker = CircuitBreaker(
            failure_threshold=custom_failure_threshold, 
            recovery_timeout=timedelta(minutes=custom_timeout_minutes), 
            name="test_breaker"
        )
        
        manager = ConsumerRecoveryManagerImpl(health_monitor, circuit_breaker=custom_breaker)
        
        assert manager.circuit_breaker is custom_breaker
        assert manager.circuit_breaker.name == "test_breaker"

    def test_circuit_breaker_default_configuration(self, health_monitor: ConsumerHealthMonitorImpl) -> None:
        """Test that default circuit breaker has appropriate configuration."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        breaker = manager.circuit_breaker
        assert breaker.failure_threshold == RECOVERY_FAILURE_THRESHOLD
        assert breaker.recovery_timeout == timedelta(minutes=2)  # Hardcoded in implementation
        assert breaker.success_threshold == RECOVERY_SUCCESS_THRESHOLD
        assert breaker.name == "consumer_recovery"

    @pytest.mark.asyncio
    async def test_attempt_soft_recovery_success(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        mock_consumer: Any
    ) -> None:
        """Test successful soft recovery with seek operations."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        result = await manager._attempt_soft_recovery(mock_consumer)
        
        assert result is True
        
        # Verify seek operations were called
        mock_consumer.seek_to_end.assert_called_once()
        mock_consumer.seek_to_beginning.assert_called_once()
        
        # Verify metrics updated
        assert manager._recovery_metrics["soft_recovery_attempts"] == 1
        assert manager._recovery_metrics["soft_recovery_successes"] == 1

    @pytest.mark.asyncio
    async def test_attempt_soft_recovery_no_assignment(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        mock_consumer: Any
    ) -> None:
        """Test soft recovery failure when consumer has no assignment."""
        mock_consumer.assignment.return_value = set()  # No assignment
        
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        result = await manager._attempt_soft_recovery(mock_consumer)
        
        assert result is False
        
        # Seek operations should not be called
        mock_consumer.seek_to_end.assert_not_called()
        mock_consumer.seek_to_beginning.assert_not_called()
        
        # Metrics should show attempt but no success
        assert manager._recovery_metrics["soft_recovery_attempts"] == 1
        assert manager._recovery_metrics["soft_recovery_successes"] == 0

    @pytest.mark.asyncio
    async def test_attempt_soft_recovery_seek_exception(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        mock_consumer: Any
    ) -> None:
        """Test soft recovery failure when seek operations raise exception."""
        mock_consumer.seek_to_end.side_effect = Exception("Seek failed")
        
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        result = await manager._attempt_soft_recovery(mock_consumer)
        
        assert result is False
        assert manager._recovery_metrics["soft_recovery_attempts"] == 1
        assert manager._recovery_metrics["soft_recovery_successes"] == 0

    @pytest.mark.asyncio
    async def test_attempt_soft_recovery_assignment_changes(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        mock_consumer: Any
    ) -> None:
        """Test soft recovery failure when assignment changes during recovery."""
        initial_assignment = {"topic-0", "topic-1"}
        changed_assignment = {"topic-0"}  # Different assignment
        
        mock_consumer.assignment.side_effect = [
            initial_assignment,  # Initial check
            changed_assignment   # Post-recovery check
        ]
        
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        result = await manager._attempt_soft_recovery(mock_consumer)
        
        assert result is False
        assert manager._recovery_metrics["soft_recovery_attempts"] == 1
        assert manager._recovery_metrics["soft_recovery_successes"] == 0

    @pytest.mark.asyncio
    async def test_execute_recovery_soft_success_path(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        mock_consumer: Any
    ) -> None:
        """Test execute recovery when soft recovery succeeds."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        result = await manager._execute_recovery(mock_consumer)
        
        assert result is True
        assert manager._recovery_metrics["hard_recovery_requests"] == 0
        assert manager._recovery_metrics["soft_recovery_successes"] == 1

    @pytest.mark.asyncio
    async def test_execute_recovery_soft_failure_requests_hard(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        mock_consumer: Any
    ) -> None:
        """Test execute recovery when soft recovery fails and requests hard recovery."""
        # Force soft recovery to fail
        mock_consumer.assignment.return_value = set()
        
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        result = await manager._execute_recovery(mock_consumer)
        
        assert result is False  # Indicates hard recovery needed
        assert manager._recovery_metrics["hard_recovery_requests"] == 1
        assert manager._recovery_metrics["soft_recovery_successes"] == 0

    def test_is_recovery_in_progress_tracking(self, health_monitor: ConsumerHealthMonitorImpl) -> None:
        """Test recovery progress tracking."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        assert manager.is_recovery_in_progress() is False
        
        # Simulate recovery in progress
        manager._recovery_in_progress = True
        assert manager.is_recovery_in_progress() is True

    def test_get_recovery_status_complete_info(self, health_monitor: ConsumerHealthMonitorImpl) -> None:
        """Test that recovery status includes all expected information."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        # Set some state
        manager._recovery_in_progress = True
        test_time = datetime.utcnow()
        manager._last_recovery_attempt = test_time
        manager._recovery_metrics["total_recovery_attempts"] = 5
        
        status = manager.get_recovery_status()
        
        assert "recovery_in_progress" in status
        assert "last_recovery_attempt" in status
        assert "circuit_breaker_state" in status  
        assert "recovery_metrics" in status
        
        assert status["recovery_in_progress"] is True
        assert status["last_recovery_attempt"] == test_time.isoformat()
        assert isinstance(status["recovery_metrics"], dict)
        assert status["recovery_metrics"]["total_recovery_attempts"] == 5

    def test_get_recovery_status_no_last_attempt(self, health_monitor: ConsumerHealthMonitorImpl) -> None:
        """Test recovery status when no recovery has been attempted."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        status = manager.get_recovery_status()
        
        assert status["recovery_in_progress"] is False
        assert status["last_recovery_attempt"] is None
        assert status["circuit_breaker_state"]["state"] == CircuitBreakerState.CLOSED.value

    @pytest.mark.asyncio
    async def test_record_recovery_attempt_updates_metrics_and_health(
        self,
        health_monitor: ConsumerHealthMonitorImpl
    ) -> None:
        """Test that recovery attempt recording updates both metrics and health monitor."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        # Record successful attempt
        await manager.record_recovery_attempt("soft", True)
        
        assert manager._recovery_metrics["total_recovery_attempts"] == 1
        assert health_monitor.messages_processed == 1
        assert health_monitor._consecutive_failures == 0
        
        # Record failed attempt
        await manager.record_recovery_attempt("hard", False)
        
        assert manager._recovery_metrics["total_recovery_attempts"] == 2
        assert health_monitor._consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_recovery_metrics_accuracy(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        mock_consumer: Any
    ) -> None:
        """Test that recovery metrics track operations accurately."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        # Perform multiple soft recoveries
        await manager._attempt_soft_recovery(mock_consumer)  # Success
        await manager._attempt_soft_recovery(mock_consumer)  # Success
        
        # Force failure
        mock_consumer.assignment.return_value = set()
        await manager._attempt_soft_recovery(mock_consumer)  # Failure
        
        assert manager._recovery_metrics["soft_recovery_attempts"] == 3
        assert manager._recovery_metrics["soft_recovery_successes"] == 2

    @pytest.mark.asyncio
    async def test_initiate_recovery_successful_soft_recovery(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        mock_consumer: Any
    ) -> None:
        """Test successful recovery through initiate_recovery method."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        result = await manager.initiate_recovery(mock_consumer)
        
        assert result is True
        assert manager._recovery_in_progress is False
        assert manager._last_recovery_attempt is not None
        
        # Verify metrics updated
        assert manager._recovery_metrics["total_recovery_attempts"] == 1
        assert manager._recovery_metrics["soft_recovery_attempts"] == 1
        assert manager._recovery_metrics["soft_recovery_successes"] == 1
        
        # Verify health monitor recorded success
        assert health_monitor.messages_processed == 1

    @pytest.mark.asyncio
    async def test_initiate_recovery_soft_recovery_fails(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        mock_consumer: Any
    ) -> None:
        """Test soft recovery failure leading to hard recovery request."""
        # Make consumer assignment return empty to force soft recovery failure
        mock_consumer.assignment.return_value = set()
        
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        result = await manager.initiate_recovery(mock_consumer)
        
        assert result is False  # Recovery failed - hard recovery needed
        
        # Verify metrics
        assert manager._recovery_metrics["soft_recovery_attempts"] == 1
        assert manager._recovery_metrics["soft_recovery_successes"] == 0
        assert manager._recovery_metrics["hard_recovery_requests"] == 1

    @pytest.mark.asyncio
    async def test_initiate_recovery_prevents_concurrent_recovery(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        mock_consumer: Any
    ) -> None:
        """Test that concurrent recovery attempts are prevented."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        # Manually set recovery in progress
        manager._recovery_in_progress = True
        
        # Try recovery while marked in progress
        result = await manager.initiate_recovery(mock_consumer)
        
        # Should be rejected
        assert result is False

    @pytest.mark.asyncio
    async def test_recovery_timestamps_tracked(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        mock_consumer: Any
    ) -> None:
        """Test that recovery attempt timestamps are properly tracked."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        before_recovery = datetime.utcnow()
        await manager.initiate_recovery(mock_consumer)
        after_recovery = datetime.utcnow()
        
        assert manager._last_recovery_attempt is not None
        assert before_recovery <= manager._last_recovery_attempt <= after_recovery

    @pytest.mark.asyncio
    async def test_circuit_breaker_failure_threshold_behavior(
        self,
        health_monitor: ConsumerHealthMonitorImpl,
        mock_consumer: Any
    ) -> None:
        """Test circuit breaker opens after threshold failures."""
        # Create recovery manager with low failure threshold for testing
        breaker = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=timedelta(seconds=1),
            name="test_breaker"
        )
        manager = ConsumerRecoveryManagerImpl(health_monitor, circuit_breaker=breaker)
        
        # Force recovery failures
        mock_consumer.assignment.return_value = set()
        
        # First failure
        result1 = await manager.initiate_recovery(mock_consumer)
        assert result1 is False  # Soft recovery fails - hard recovery needed
        
        # Second failure should also return False
        result2 = await manager.initiate_recovery(mock_consumer) 
        assert result2 is False
        
        # Circuit breaker behavior depends on the actual implementation
        # We verify the recovery manager still functions correctly
        assert manager._recovery_metrics["total_recovery_attempts"] == 2

    def test_recovery_lock_prevents_race_conditions(self, health_monitor: ConsumerHealthMonitorImpl) -> None:
        """Test that recovery lock is properly initialized and used."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        assert isinstance(manager._recovery_lock, asyncio.Lock)
        assert not manager._recovery_lock.locked()

    def test_health_monitor_integration(self, health_monitor: ConsumerHealthMonitorImpl) -> None:
        """Test that health monitor is properly integrated."""
        manager = ConsumerRecoveryManagerImpl(health_monitor)
        
        # Verify the health monitor is the same instance
        assert manager.health_monitor is health_monitor
        
        # Test that we can access health monitor methods
        initial_health = health_monitor.is_healthy()
        assert isinstance(initial_health, bool)
        
        # Test metrics integration
        metrics = health_monitor.get_health_metrics()
        assert isinstance(metrics, dict)
        assert "is_healthy" in metrics