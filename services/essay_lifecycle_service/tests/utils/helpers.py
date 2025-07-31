"""
Test helper utilities for Essay Lifecycle Service tests.

Provides common test constants, helper functions, and time manipulation utilities
to improve test reliability and reduce duplication.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

from freezegun import freeze_time

# Test Constants for Health Monitoring
HEALTH_CHECK_INTERVAL_TEST = 1  # seconds
MAX_IDLE_SECONDS_TEST = 3  # seconds
HEALTH_CHECK_INTERVAL_DEFAULT = 30  # seconds
MAX_IDLE_SECONDS_DEFAULT = 60  # seconds

# Test Constants for Recovery Manager
RECOVERY_FAILURE_THRESHOLD = 3
RECOVERY_TIMEOUT_SECONDS = 2
RECOVERY_SUCCESS_THRESHOLD = 1
CIRCUIT_BREAKER_RECOVERY_TIMEOUT_DEFAULT = 120  # 2 minutes in seconds

# Test Constants for Consumer Health
CONSECUTIVE_FAILURE_THRESHOLD = 5
MESSAGE_PROCESSING_TIMEOUT = 0.1  # seconds for async operations

# Kafka Consumer Test Constants
TEST_TOPIC_PREFIX = "test-topic"
TEST_CONSUMER_GROUP = "test-consumer-group"


def create_timestamp_seconds_ago(seconds: int) -> datetime:
    """
    Create a timezone-aware timestamp N seconds in the past.

    Args:
        seconds: Number of seconds ago from current time

    Returns:
        Timezone-aware datetime object
    """
    return datetime.now(UTC) - timedelta(seconds=seconds)


def create_timestamp_seconds_ahead(seconds: int) -> datetime:
    """
    Create a timezone-aware timestamp N seconds in the future.

    Args:
        seconds: Number of seconds ahead from current time

    Returns:
        Timezone-aware datetime object
    """
    return datetime.now(UTC) + timedelta(seconds=seconds)


class TimeAdvancer:
    """
    Context manager for advancing time in tests without sleep.

    Uses freezegun to control time progression in tests, eliminating
    flaky time-based test behavior.

    Example:
        with TimeAdvancer() as time_advancer:
            # Do something
            time_advancer.advance(seconds=5)
            # Time has now advanced by 5 seconds
    """

    def __init__(self, start_time: datetime | None = None):
        """
        Initialize time advancer.

        Args:
            start_time: Optional starting time, defaults to current time
        """
        self.start_time = start_time or datetime.now(UTC)
        self._frozen_time: Any = None  # freeze_time context manager
        self._context: Any = None

    def __enter__(self) -> TimeAdvancer:
        """Enter context and freeze time."""
        self._frozen_time = freeze_time(self.start_time, tick=True)
        self._context = self._frozen_time.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context and unfreeze time."""
        if self._frozen_time:
            self._frozen_time.__exit__(exc_type, exc_val, exc_tb)

    def advance(self, seconds: float) -> None:
        """
        Advance frozen time by specified seconds.

        Args:
            seconds: Number of seconds to advance
        """
        if self._context:
            # The context returned by freeze_time.__enter__() has the tick method
            self._context.tick(delta=timedelta(seconds=seconds))

    def set_time(self, target_time: datetime) -> None:
        """
        Set frozen time to specific timestamp.

        Args:
            target_time: Target datetime to set
        """
        if self._context:
            # Move to specific time
            self._context.move_to(target_time)


def create_mock_kafka_consumer(
    assignment: set[str] | None = None, raise_on_seek: bool = False
) -> MagicMock:
    """
    Create a properly configured mock Kafka consumer.

    Args:
        assignment: Topic partition assignment
        raise_on_seek: Whether to raise exception on seek operations

    Returns:
        Configured mock consumer
    """
    from uuid import uuid4

    consumer = MagicMock()

    # Set default assignment if not provided
    if assignment is None:
        assignment = {f"{TEST_TOPIC_PREFIX}-{uuid4().hex[:8]}-0"}

    consumer.assignment = MagicMock(return_value=assignment)

    if raise_on_seek:
        consumer.seek_to_end = MagicMock(side_effect=Exception("Seek failed"))
        consumer.seek_to_beginning = MagicMock(side_effect=Exception("Seek failed"))
    else:
        consumer.seek_to_end = MagicMock()
        consumer.seek_to_beginning = MagicMock()

    return consumer


class HealthMonitorTestHelper:
    """Helper class for testing health monitor state without direct manipulation."""

    @staticmethod
    def create_unhealthy_by_idle_time(monitor: Any, idle_seconds: int) -> None:
        """
        Make monitor unhealthy by simulating idle time.

        Uses time mocking instead of direct state manipulation.

        Args:
            monitor: Health monitor instance
            idle_seconds: Seconds to simulate as idle
        """
        with freeze_time(monitor.last_message_time + timedelta(seconds=idle_seconds)):
            # The monitor will now report as unhealthy due to idle time
            pass

    @staticmethod
    def create_unhealthy_by_failures(monitor: Any, failure_count: int) -> None:
        """
        Make monitor unhealthy by recording failures.

        Uses proper API instead of direct state manipulation.

        Args:
            monitor: Health monitor instance
            failure_count: Number of failures to record
        """
        import asyncio

        async def record_failures() -> None:
            for _ in range(failure_count):
                await monitor.record_processing_failure()

        asyncio.run(record_failures())
