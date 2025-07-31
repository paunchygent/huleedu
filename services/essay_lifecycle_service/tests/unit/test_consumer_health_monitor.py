"""
Unit tests for ConsumerHealthMonitorImpl for ELS Kafka consumer self-healing.

Tests health monitoring functionality including message processing tracking,
failure detection, idle time monitoring, and health metrics generation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from freezegun import freeze_time

from services.essay_lifecycle_service.implementations.consumer_health_monitor_impl import (
    ConsumerHealthMonitorImpl,
)
from services.essay_lifecycle_service.tests.utils.helpers import (
    CONSECUTIVE_FAILURE_THRESHOLD,
    HEALTH_CHECK_INTERVAL_DEFAULT,
    MAX_IDLE_SECONDS_DEFAULT,
    TimeAdvancer,
)


@pytest.mark.unit
class TestConsumerHealthMonitorImpl:
    """Test suite for consumer health monitoring implementation."""

    def test_initialization_sets_default_values(self) -> None:
        """Test that monitor initializes with correct default values."""
        with freeze_time("2024-01-01 12:00:00"):
            monitor = ConsumerHealthMonitorImpl()

            assert monitor.health_check_interval == HEALTH_CHECK_INTERVAL_DEFAULT
            assert monitor.max_idle_seconds == MAX_IDLE_SECONDS_DEFAULT
            assert monitor.messages_processed == 0
            assert monitor._consecutive_failures == 0

            # Should initialize with current frozen timestamp
            expected_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
            assert monitor.last_message_time == expected_time

    def test_initialization_with_custom_values(self) -> None:
        """Test monitor initialization with custom configuration."""
        monitor = ConsumerHealthMonitorImpl(health_check_interval=45, max_idle_seconds=120)

        assert monitor.health_check_interval == 45
        assert monitor.max_idle_seconds == 120

    @pytest.mark.asyncio
    async def test_record_message_processed_updates_state(self) -> None:
        """Test that recording processed message updates all relevant state."""
        monitor = ConsumerHealthMonitorImpl()

        # Set initial failure count
        monitor._consecutive_failures = 3
        initial_time = monitor.last_message_time

        await monitor.record_message_processed()

        assert monitor.messages_processed == 1
        assert monitor._consecutive_failures == 0  # Should reset on success
        assert monitor.last_message_time > initial_time

    @pytest.mark.asyncio
    async def test_record_processing_failure_increments_count(self) -> None:
        """Test that recording failure increments consecutive failure count."""
        monitor = ConsumerHealthMonitorImpl()

        await monitor.record_processing_failure()
        assert monitor._consecutive_failures == 1

        await monitor.record_processing_failure()
        assert monitor._consecutive_failures == 2

    @pytest.mark.asyncio
    async def test_multiple_processed_messages_increment_counter(self) -> None:
        """Test that multiple processed messages increment counter correctly."""
        monitor = ConsumerHealthMonitorImpl()

        for i in range(5):
            await monitor.record_message_processed()
            assert monitor.messages_processed == i + 1

    def test_is_healthy_when_recently_active_no_failures(self) -> None:
        """Test healthy status when recently active with no failures."""
        monitor = ConsumerHealthMonitorImpl(max_idle_seconds=60)

        # Recent activity, no failures
        assert monitor.is_healthy() is True

    def test_is_healthy_false_when_idle_too_long(self) -> None:
        """Test unhealthy status when idle longer than threshold."""
        with TimeAdvancer() as time_advancer:
            monitor = ConsumerHealthMonitorImpl(max_idle_seconds=MAX_IDLE_SECONDS_DEFAULT)

            # Advance time beyond idle threshold
            time_advancer.advance(seconds=MAX_IDLE_SECONDS_DEFAULT + 60)

            assert monitor.is_healthy() is False

    def test_is_healthy_false_when_too_many_failures(self) -> None:
        """Test unhealthy status when consecutive failures exceed threshold."""
        monitor = ConsumerHealthMonitorImpl(max_idle_seconds=MAX_IDLE_SECONDS_DEFAULT)

        # Set high failure count using the constant
        monitor._consecutive_failures = CONSECUTIVE_FAILURE_THRESHOLD

        assert monitor.is_healthy() is False

    def test_is_healthy_false_when_idle_and_failures(self) -> None:
        """Test unhealthy status when both idle and have failures."""
        with TimeAdvancer() as time_advancer:
            monitor = ConsumerHealthMonitorImpl(max_idle_seconds=MAX_IDLE_SECONDS_DEFAULT)

            # Set failures below threshold
            monitor._consecutive_failures = 3  # Below threshold but combined with idle

            # Advance time beyond idle threshold
            time_advancer.advance(seconds=MAX_IDLE_SECONDS_DEFAULT * 2)

            assert monitor.is_healthy() is False

    def test_should_check_health_initially_false(self) -> None:
        """Test that health check is not needed immediately after creation."""
        monitor = ConsumerHealthMonitorImpl(health_check_interval=30)

        # Just created, shouldn't need check yet
        assert monitor.should_check_health() is False

    def test_should_check_health_true_after_interval(self) -> None:
        """Test that health check is needed after interval elapses."""
        with TimeAdvancer() as time_advancer:
            monitor = ConsumerHealthMonitorImpl(health_check_interval=HEALTH_CHECK_INTERVAL_DEFAULT)

            # Advance time past health check interval
            time_advancer.advance(seconds=HEALTH_CHECK_INTERVAL_DEFAULT + 15)

            assert monitor.should_check_health() is True

    def test_should_check_health_updates_last_check_time(self) -> None:
        """Test that calling should_check_health updates the last check time."""
        monitor = ConsumerHealthMonitorImpl(health_check_interval=30)

        # Set old check time to trigger update
        old_time = datetime.now(UTC) - timedelta(seconds=45)
        monitor._last_health_check = old_time

        result = monitor.should_check_health()

        assert result is True
        assert monitor._last_health_check > old_time

    def test_get_health_metrics_includes_all_fields(self) -> None:
        """Test that health metrics include all expected fields."""
        monitor = ConsumerHealthMonitorImpl(health_check_interval=45, max_idle_seconds=120)

        # Set some state
        monitor.messages_processed = 10
        monitor._consecutive_failures = 2

        metrics = monitor.get_health_metrics()

        assert "messages_processed" in metrics
        assert "idle_seconds" in metrics
        assert "consecutive_failures" in metrics
        assert "is_healthy" in metrics
        assert "last_message_time" in metrics
        assert "health_check_interval" in metrics
        assert "max_idle_seconds" in metrics

        assert metrics["messages_processed"] == 10
        assert metrics["consecutive_failures"] == 2
        assert metrics["health_check_interval"] == 45
        assert metrics["max_idle_seconds"] == 120
        assert isinstance(metrics["idle_seconds"], float)
        assert isinstance(metrics["is_healthy"], bool)

    def test_get_health_metrics_idle_seconds_calculation(self) -> None:
        """Test that idle seconds are calculated correctly in metrics."""
        with TimeAdvancer() as time_advancer:
            monitor = ConsumerHealthMonitorImpl()

            # Advance time by known amount
            idle_time = 30
            time_advancer.advance(seconds=idle_time)

            metrics = monitor.get_health_metrics()

            # Should calculate idle time approximately (allow small floating point differences)
            assert abs(metrics["idle_seconds"] - idle_time) < 0.1

    @pytest.mark.asyncio
    async def test_failure_threshold_boundary_conditions(self) -> None:
        """Test behavior at failure threshold boundaries."""
        monitor = ConsumerHealthMonitorImpl()

        # One less than threshold should still be healthy
        for _ in range(CONSECUTIVE_FAILURE_THRESHOLD - 1):
            await monitor.record_processing_failure()
        assert monitor.is_healthy() is True

        # Reaching threshold should make unhealthy
        await monitor.record_processing_failure()
        assert monitor.is_healthy() is False

    def test_idle_threshold_boundary_conditions(self) -> None:
        """Test behavior at idle time threshold boundaries."""
        with TimeAdvancer() as time_advancer:
            monitor = ConsumerHealthMonitorImpl(max_idle_seconds=MAX_IDLE_SECONDS_DEFAULT)

            # Just before threshold - should be healthy
            time_advancer.advance(seconds=MAX_IDLE_SECONDS_DEFAULT - 1)
            assert monitor.is_healthy() is True

            # Just past threshold - should be unhealthy
            time_advancer.advance(seconds=2)  # Now at MAX_IDLE_SECONDS_DEFAULT + 1
            assert monitor.is_healthy() is False

    @pytest.mark.asyncio
    async def test_record_processed_resets_failures_completely(self) -> None:
        """Test that successful processing completely resets failure count."""
        monitor = ConsumerHealthMonitorImpl()

        # Build up failures
        for _ in range(4):
            await monitor.record_processing_failure()
        assert monitor._consecutive_failures == 4

        # Single success should reset to 0
        await monitor.record_message_processed()
        assert monitor._consecutive_failures == 0

        # Should be healthy again
        assert monitor.is_healthy() is True

    def test_health_check_interval_zero_always_checks(self) -> None:
        """Test that zero health check interval means always check."""
        monitor = ConsumerHealthMonitorImpl(health_check_interval=0)

        # Should always return True for zero interval
        assert monitor.should_check_health() is True
        assert monitor.should_check_health() is True  # Multiple calls

    @pytest.mark.asyncio
    async def test_concurrent_health_operations_thread_safety(self) -> None:
        """Test that concurrent operations maintain state consistency."""
        monitor = ConsumerHealthMonitorImpl()

        # Simulate concurrent operations
        import asyncio

        tasks = []
        for _ in range(10):
            tasks.append(monitor.record_message_processed())
        for _ in range(5):
            tasks.append(monitor.record_processing_failure())

        await asyncio.gather(*tasks)

        # Final state should be consistent - messages processed should be exact
        assert monitor.messages_processed == 10

        # Failure count could be 0 or 5 depending on execution order
        # but should be one of these values (no corruption)
        assert monitor._consecutive_failures in [0, 5]

    def test_metrics_timestamp_format(self) -> None:
        """Test that metrics timestamp is in ISO format."""
        monitor = ConsumerHealthMonitorImpl()

        metrics = monitor.get_health_metrics()
        timestamp = metrics["last_message_time"]

        # Should be valid ISO format
        assert isinstance(timestamp, str)
        # Should be parseable back to datetime
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert isinstance(parsed, datetime)

    def test_large_message_count_handling(self) -> None:
        """Test handling of large message processing counts."""
        monitor = ConsumerHealthMonitorImpl()

        # Set large count directly
        monitor.messages_processed = 1_000_000

        metrics = monitor.get_health_metrics()
        assert metrics["messages_processed"] == 1_000_000

        # Should still function normally
        assert isinstance(monitor.is_healthy(), bool)
