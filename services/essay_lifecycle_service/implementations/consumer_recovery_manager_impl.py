"""
Consumer Recovery Manager implementation for ELS Kafka consumer self-healing.

This module implements graduated recovery strategies using CircuitBreaker pattern
to prevent recovery loops and ensure reliable consumer operation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiokafka import AIOKafkaConsumer

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker

from services.essay_lifecycle_service.protocols import (
    ConsumerRecoveryManager,
    KafkaConsumerHealthMonitor,
)

logger = create_service_logger("consumer_recovery_manager")


class ConsumerRecoveryManagerImpl(ConsumerRecoveryManager):
    """
    Implementation of consumer recovery manager with graduated recovery strategy.

    Uses CircuitBreaker to prevent recovery loops and implements:
    1. Soft recovery: seek operations to reset consumer position
    2. Hard recovery: consumer recreation (handled by caller)

    The circuit breaker prevents excessive recovery attempts and provides
    observability into recovery success/failure patterns.
    """

    def __init__(
        self,
        health_monitor: KafkaConsumerHealthMonitor,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        """
        Initialize recovery manager with health monitoring and circuit breaker.

        Args:
            health_monitor: Health monitor for tracking consumer state
            circuit_breaker: Optional circuit breaker for recovery attempts
        """
        self.health_monitor = health_monitor
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=3,  # Allow 3 recovery failures before opening
            recovery_timeout=timedelta(minutes=2),  # Wait 2 minutes before retry
            success_threshold=1,  # Single success closes circuit
            expected_exception=Exception,
            name="consumer_recovery",
        )

        self._recovery_in_progress = False
        self._recovery_lock = asyncio.Lock()
        self._last_recovery_attempt: datetime | None = None
        self._recovery_metrics = {
            "soft_recovery_attempts": 0,
            "soft_recovery_successes": 0,
            "hard_recovery_requests": 0,
            "total_recovery_attempts": 0,
        }

    async def initiate_recovery(self, consumer: AIOKafkaConsumer) -> bool:
        """
        Initiate graduated recovery process for unhealthy consumer.

        Implements graduated recovery strategy:
        1. First attempt: Soft recovery with seek operations
        2. If soft recovery fails: Request hard recovery (consumer recreation)

        Uses circuit breaker to prevent recovery loops.

        Args:
            consumer: The Kafka consumer to recover

        Returns:
            True if recovery was successful, False if failed or circuit open
        """
        async with self._recovery_lock:
            if self._recovery_in_progress:
                logger.warning("Recovery already in progress, skipping duplicate request")
                return False

            self._recovery_in_progress = True
            self._last_recovery_attempt = datetime.utcnow()

        try:
            # Use circuit breaker to control recovery attempts
            result: bool = await self.circuit_breaker.call(self._execute_recovery, consumer)
            await self.record_recovery_attempt("graduated", True)
            return result

        except Exception as e:
            logger.error(
                f"Consumer recovery failed: {e}",
                extra={
                    "consumer_assignment": str(consumer.assignment()) if consumer else "none",
                    "recovery_metrics": self._recovery_metrics,
                    "error": str(e),
                },
                exc_info=True,
            )

            await self.record_recovery_attempt("graduated", False)
            return False

        finally:
            async with self._recovery_lock:
                self._recovery_in_progress = False

    async def _execute_recovery(self, consumer: AIOKafkaConsumer) -> bool:
        """
        Execute the actual recovery logic with graduated strategy.

        Args:
            consumer: Consumer to recover

        Returns:
            True if recovery successful, False if hard recovery needed
        """
        logger.info("Starting graduated consumer recovery")

        # Step 1: Attempt soft recovery
        soft_recovery_success = await self._attempt_soft_recovery(consumer)

        if soft_recovery_success:
            logger.info("Soft recovery completed successfully")
            return True

        # Step 2: Soft recovery failed, signal need for hard recovery
        logger.warning("Soft recovery failed, hard recovery (consumer recreation) needed")
        self._recovery_metrics["hard_recovery_requests"] += 1

        # Return False to indicate caller should recreate consumer
        # This is part of the graduated strategy - we don't recreate here
        # to maintain separation of concerns
        return False

    async def _attempt_soft_recovery(self, consumer: AIOKafkaConsumer) -> bool:
        """
        Attempt soft recovery using seek operations to reset consumer position.

        Args:
            consumer: Consumer to recover

        Returns:
            True if soft recovery successful, False otherwise
        """
        self._recovery_metrics["soft_recovery_attempts"] += 1

        try:
            logger.info("Attempting soft recovery with seek operations")

            # Get current assignment
            assignment = consumer.assignment()
            if not assignment:
                logger.warning("Consumer has no topic assignment, cannot perform soft recovery")
                return False

            logger.debug(f"Consumer assignment: {assignment}")

            # Seek to end then back to beginning to reset consumer state
            # This helps with stuck consumer scenarios
            logger.debug("Seeking to end of partitions")
            consumer.seek_to_end()

            # Small delay to ensure seek operations complete
            await asyncio.sleep(0.1)

            logger.debug("Seeking to beginning of partitions")
            consumer.seek_to_beginning()

            # Another small delay
            await asyncio.sleep(0.1)

            # Verify consumer is responsive by checking assignment again
            post_recovery_assignment = consumer.assignment()
            if post_recovery_assignment != assignment:
                logger.warning("Consumer assignment changed during recovery")
                return False

            logger.info("Soft recovery seek operations completed successfully")
            self._recovery_metrics["soft_recovery_successes"] += 1
            return True

        except Exception as e:
            logger.error(f"Soft recovery failed: {e}", exc_info=True)
            return False

    def is_recovery_in_progress(self) -> bool:
        """Check if a recovery operation is currently in progress."""
        return self._recovery_in_progress

    def get_recovery_status(self) -> dict[str, Any]:
        """Get current recovery status and metrics for observability."""
        return {
            "recovery_in_progress": self._recovery_in_progress,
            "last_recovery_attempt": (
                self._last_recovery_attempt.isoformat() if self._last_recovery_attempt else None
            ),
            "circuit_breaker_state": self.circuit_breaker.get_state(),
            "recovery_metrics": self._recovery_metrics.copy(),
        }

    async def record_recovery_attempt(self, recovery_type: str, success: bool) -> None:
        """Record recovery attempt for metrics and circuit breaker management."""
        self._recovery_metrics["total_recovery_attempts"] += 1

        # Record with health monitor for overall health tracking
        if success:
            await self.health_monitor.record_message_processed()
        else:
            await self.health_monitor.record_processing_failure()

        logger.info(
            "Recovery attempt recorded",
            extra={
                "recovery_type": recovery_type,
                "success": success,
                "total_attempts": self._recovery_metrics["total_recovery_attempts"],
                "circuit_state": self.circuit_breaker.state.value,
            },
        )
