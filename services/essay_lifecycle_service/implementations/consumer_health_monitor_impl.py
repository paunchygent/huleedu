"""
Consumer health monitoring implementation for Kafka consumer self-healing.

This module provides health monitoring capabilities for Kafka consumers to enable
self-healing mechanisms when consumer processing stalls or fails.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger

from services.essay_lifecycle_service.protocols import KafkaConsumerHealthMonitor

logger = create_service_logger("essay_lifecycle_service.consumer_health_monitor")

UTC = UTC


class ConsumerHealthMonitorImpl(KafkaConsumerHealthMonitor):
    """
    Implementation of Kafka consumer health monitoring for self-healing mechanism.

    Tracks message processing activity, failure rates, and provides health status
    to enable proactive consumer restarts when processing stalls.
    """

    def __init__(self, health_check_interval: int = 30, max_idle_seconds: int = 60) -> None:
        """
        Initialize health monitor with configurable thresholds.

        Args:
            health_check_interval: Seconds between periodic health checks
            max_idle_seconds: Maximum seconds without message processing before unhealthy
        """
        self.last_message_time = datetime.now(UTC)
        self.messages_processed = 0
        self.health_check_interval = health_check_interval
        self.max_idle_seconds = max_idle_seconds
        self._consecutive_failures = 0
        self._last_health_check = datetime.now(UTC)

        logger.info(
            "Consumer health monitor initialized",
            extra={
                "health_check_interval": health_check_interval,
                "max_idle_seconds": max_idle_seconds,
            },
        )

    async def record_message_processed(self) -> None:
        """Record successful message processing and reset failure counters."""
        self.last_message_time = datetime.now(UTC)
        self.messages_processed += 1
        self._consecutive_failures = 0  # Reset on success

        logger.debug(
            "Message processed successfully",
            extra={
                "messages_processed": self.messages_processed,
                "consecutive_failures_reset": True,
            },
        )

    async def record_processing_failure(self) -> None:
        """Record message processing failure for health status calculation."""
        self._consecutive_failures += 1

        logger.warning(
            "Message processing failure recorded",
            extra={
                "consecutive_failures": self._consecutive_failures,
                "failure_threshold_breached": self._consecutive_failures >= 5,
            },
        )

    def is_healthy(self) -> bool:
        """
        Check if consumer is healthy based on recent activity and failure rate.

        Consumer is considered healthy if:
        - Messages processed recently (within max_idle_seconds), AND
        - No excessive consecutive failures (< 5)

        Returns:
            True if consumer is healthy, False otherwise
        """
        idle_time = (datetime.now(UTC) - self.last_message_time).total_seconds()
        is_active = idle_time < self.max_idle_seconds
        has_low_failures = self._consecutive_failures < 5

        healthy = is_active and has_low_failures

        logger.debug(
            "Health check performed",
            extra={
                "idle_seconds": idle_time,
                "consecutive_failures": self._consecutive_failures,
                "is_active": is_active,
                "has_low_failures": has_low_failures,
                "is_healthy": healthy,
            },
        )

        return healthy

    def should_check_health(self) -> bool:
        """
        Check if it's time to perform a periodic health check.

        Returns:
            True if health check interval has elapsed, False otherwise
        """
        time_since_check = (datetime.now(UTC) - self._last_health_check).total_seconds()
        should_check = time_since_check >= self.health_check_interval

        if should_check:
            self._last_health_check = datetime.now(UTC)
            logger.debug(
                "Health check interval reached",
                extra={
                    "time_since_last_check": time_since_check,
                    "health_check_interval": self.health_check_interval,
                },
            )

        return should_check

    def get_health_metrics(self) -> dict[str, Any]:
        """
        Get current health metrics for observability and monitoring.

        Returns:
            Dictionary containing health metrics for Prometheus/logging
        """
        idle_time = (datetime.now(UTC) - self.last_message_time).total_seconds()

        metrics = {
            "messages_processed": self.messages_processed,
            "idle_seconds": idle_time,
            "consecutive_failures": self._consecutive_failures,
            "is_healthy": self.is_healthy(),
            "last_message_time": self.last_message_time.isoformat(),
            "health_check_interval": self.health_check_interval,
            "max_idle_seconds": self.max_idle_seconds,
        }

        logger.debug("Health metrics collected", extra=metrics)

        return metrics
