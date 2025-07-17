"""
Circuit Breaker pattern implementation for service resilience.

This module provides a circuit breaker to prevent cascading failures
in distributed systems by temporarily blocking calls to failing services.
"""

import asyncio
from datetime import datetime, timedelta

# Import TYPE_CHECKING to avoid circular imports
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Type, TypeVar, cast

from common_core import CircuitBreakerState
from opentelemetry import trace

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from huleedu_service_libs.resilience.metrics_bridge import CircuitBreakerMetrics

logger = create_service_logger("circuit_breaker")

T = TypeVar("T")


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, message: str, last_failure_time: Optional[datetime] = None):
        super().__init__(message)
        self.last_failure_time = last_failure_time


class CircuitBreaker:
    """
    Circuit breaker for service resilience.

    The circuit breaker prevents cascading failures by monitoring failure rates
    and temporarily blocking calls to failing services.

    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Too many failures, requests are blocked
    - HALF_OPEN: Testing recovery, limited requests allowed
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: timedelta = timedelta(seconds=60),
        success_threshold: int = 2,
        expected_exception: Type[Exception] = Exception,
        name: Optional[str] = None,
        tracer: Optional[trace.Tracer] = None,
        metrics: Optional["CircuitBreakerMetrics"] = None,
        service_name: Optional[str] = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Time to wait before attempting recovery
            success_threshold: Successes needed in half-open to close circuit
            expected_exception: Exception type to count as failure
            name: Circuit breaker name for logging/metrics
            tracer: OpenTelemetry tracer for instrumentation
            metrics: Optional metrics bridge for Prometheus integration
            service_name: Service name for metrics labeling
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.expected_exception = expected_exception
        self.name = name or "circuit_breaker"
        self._explicit_tracer = tracer
        self._lazy_tracer: Optional[trace.Tracer] = None
        self.metrics = metrics
        self.service_name = service_name or "unknown"

        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitBreakerState.CLOSED
        self._lock = asyncio.Lock()

        # Initialize metrics with current state
        if self.metrics:
            self.metrics.set_state(self.name, self.state, self.service_name)

    @property
    def tracer(self) -> trace.Tracer:
        """
        Get tracer instance using lazy initialization.

        Returns explicit tracer if provided, otherwise initializes
        and caches a default tracer on first access.
        """
        if self._explicit_tracer is not None:
            return self._explicit_tracer

        if self._lazy_tracer is None:
            self._lazy_tracer = trace.get_tracer(__name__)

        return self._lazy_tracer

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func execution

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: If func raises an exception
        """
        # Check circuit state
        async with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    self._record_blocked_call()
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self.name}' is OPEN",
                        self.last_failure_time,
                    )

        # Execute with tracing
        with self.tracer.start_as_current_span(
            f"circuit_breaker.{self.name}.{func.__name__}",
            attributes={
                "circuit.name": self.name,
                "circuit.state": self.state.value,
                "circuit.failure_count": self.failure_count,
                "circuit.success_count": self.success_count,
            },
        ) as span:
            try:
                # Execute the function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Record success
                await self._on_success()
                span.set_attribute("circuit.call_result", "success")

                # Record successful call metrics
                if self.metrics:
                    self.metrics.increment_calls(self.name, "success", self.service_name)

                return cast(T, result)

            except self.expected_exception as e:
                # Record failure
                await self._on_failure()
                span.record_exception(e)
                span.set_attribute("circuit.call_result", "failure")

                # Record failed call metrics
                if self.metrics:
                    self.metrics.increment_calls(self.name, "failure", self.service_name)

                raise

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.success_count += 1
                logger.info(
                    f"Circuit breaker '{self.name}' success in HALF_OPEN "
                    f"({self.success_count}/{self.success_threshold})"
                )

                if self.success_count >= self.success_threshold:
                    self._transition_to_closed()
            elif self.state == CircuitBreakerState.CLOSED:
                # Reset failure count on success in closed state
                self.failure_count = 0

    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self._lock:
            self.last_failure_time = datetime.utcnow()

            if self.state == CircuitBreakerState.CLOSED:
                self.failure_count += 1
                logger.warning(
                    f"Circuit breaker '{self.name}' failure "
                    f"({self.failure_count}/{self.failure_threshold})"
                )

                if self.failure_count >= self.failure_threshold:
                    self._transition_to_open()

            elif self.state == CircuitBreakerState.HALF_OPEN:
                # Single failure in half-open returns to open
                self._transition_to_open()

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True

        time_since_failure = datetime.utcnow() - self.last_failure_time
        return time_since_failure >= self.recovery_timeout

    def _transition_to_open(self) -> None:
        """Transition to OPEN state."""
        previous_state = self.state
        self.state = CircuitBreakerState.OPEN
        self.success_count = 0

        # Record metrics for state transition
        if self.metrics:
            self.metrics.record_state_change(
                self.name, previous_state, self.state, self.service_name
            )

        logger.error(
            f"Circuit breaker '{self.name}' transitioned to OPEN. "
            f"Blocking calls for {self.recovery_timeout.total_seconds()}s"
        )

    def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN state."""
        previous_state = self.state
        self.state = CircuitBreakerState.HALF_OPEN
        self.success_count = 0
        self.failure_count = 0

        # Record metrics for state transition
        if self.metrics:
            self.metrics.record_state_change(
                self.name, previous_state, self.state, self.service_name
            )

        logger.info(f"Circuit breaker '{self.name}' transitioned to HALF_OPEN. Testing recovery...")

    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state."""
        previous_state = self.state
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0

        # Record metrics for state transition
        if self.metrics:
            self.metrics.record_state_change(
                self.name, previous_state, self.state, self.service_name
            )

        logger.info(f"Circuit breaker '{self.name}' transitioned to CLOSED.")

    def _record_blocked_call(self) -> None:
        """Record metrics for blocked call."""
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            current_span.set_attribute("circuit.blocked", True)
            current_span.set_attribute("circuit.state", self.state.value)

        # Record blocked call metrics
        if self.metrics:
            self.metrics.record_blocked_call(self.name, self.service_name)

    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": (
                self.last_failure_time.isoformat() if self.last_failure_time else None
            ),
        }

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        previous_state = self.state
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None

        # Record metrics for manual reset
        if self.metrics and previous_state != CircuitBreakerState.CLOSED:
            self.metrics.record_state_change(
                self.name, previous_state, self.state, self.service_name
            )

        logger.info(f"Circuit breaker '{self.name}' manually reset to CLOSED.")


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: timedelta = timedelta(seconds=60),
    success_threshold: int = 2,
    expected_exception: Type[Exception] = Exception,
    name: Optional[str] = None,
) -> Callable:
    """
    Decorator to apply circuit breaker pattern to a function.

    Usage:
        @circuit_breaker(failure_threshold=3, recovery_timeout=timedelta(seconds=30))
        async def call_external_service():
            ...
    """

    def decorator(func: Callable) -> Callable:
        # Create circuit breaker instance
        breaker_name = name or f"{func.__module__}.{func.__name__}"
        breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            success_threshold=success_threshold,
            expected_exception=expected_exception,
            name=breaker_name,
        )

        async def async_wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)

        def sync_wrapper(*args, **kwargs):
            # For sync functions, we need to run in an event loop
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(breaker.call(func, *args, **kwargs))

        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
