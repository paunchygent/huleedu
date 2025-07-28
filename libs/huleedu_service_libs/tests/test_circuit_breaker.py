"""
Unit tests for Circuit Breaker infrastructure.

Tests circuit breaker state machine, resilient client wrapper, registry management,
and metrics integration. Follows HuleEdu testing patterns with comprehensive coverage
of all state transitions and edge cases.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pytest
from common_core import CircuitBreakerState
from huleedu_service_libs.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    circuit_breaker,
)
from huleedu_service_libs.resilience.metrics_bridge import (
    CircuitBreakerMetrics,
)
from opentelemetry import trace
from opentelemetry.trace import Tracer

# Real handler functions for testing (not mocks)
# Circuit breaker expects Callable[..., T] but handles async functions by awaiting them internally.
# We use TYPE_CHECKING to provide correct signatures for type checking while keeping async
# behavior at runtime.

if TYPE_CHECKING:
    # For type checking: functions appear to return final result type (what circuit breaker expects)
    def successful_async_function(value: str) -> str: ...
    def successful_sync_function(value: str) -> str: ...
    def failing_async_function(failure_message: str) -> str: ...
    def failing_sync_function(failure_message: str) -> str: ...
    def unexpected_error_function() -> str: ...
else:
    # At runtime: actual implementations that circuit breaker can handle correctly
    async def successful_async_function(value: str) -> str:
        """Real async function that succeeds."""
        return f"success_{value}"

    def successful_sync_function(value: str) -> str:
        """Real sync function that succeeds."""
        return f"success_{value}"

    async def failing_async_function(failure_message: str) -> str:
        """Real async function that raises ValueError."""
        raise ValueError(failure_message)

    def failing_sync_function(failure_message: str) -> str:
        """Real sync function that raises ValueError."""
        raise ValueError(failure_message)

    async def unexpected_error_function() -> str:
        """Real async function that raises unexpected exception."""
        raise RuntimeError("Unexpected error")


# Test fixtures and utilities
@pytest.fixture
def mock_metrics() -> Mock:
    """Provide mock metrics bridge for testing."""
    metrics: Mock = Mock(spec=CircuitBreakerMetrics)
    return metrics


@pytest.fixture
def test_circuit_breaker(mock_metrics: Mock) -> CircuitBreaker:
    """Provide circuit breaker with test configuration."""
    return CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=timedelta(seconds=1),
        success_threshold=2,
        expected_exception=ValueError,
        name="test_breaker",
        metrics=mock_metrics,
        service_name="test_service",
    )


@pytest.fixture
def test_tracer() -> Tracer:
    """Provide OpenTelemetry tracer for testing."""
    return trace.get_tracer("test_tracer")


class TestCircuitBreakerError:
    """Test CircuitBreakerError exception class."""

    def test_error_creation_with_message_only(self) -> None:
        """Test creating CircuitBreakerError with just message."""
        error = CircuitBreakerError("Circuit is open")

        assert str(error) == "Circuit is open"
        assert error.last_failure_time is None

    def test_error_creation_with_failure_time(self) -> None:
        """Test creating CircuitBreakerError with failure time."""
        failure_time: datetime = datetime.now(timezone.utc)
        error: CircuitBreakerError = CircuitBreakerError("Circuit is open", failure_time)

        assert str(error) == "Circuit is open"
        assert error.last_failure_time == failure_time

    def test_error_inheritance(self) -> None:
        """Test that CircuitBreakerError is proper Exception subclass."""
        error: CircuitBreakerError = CircuitBreakerError("Test error")

        assert isinstance(error, Exception)
        assert isinstance(error, CircuitBreakerError)


class TestCircuitBreakerInitialization:
    """Test CircuitBreaker initialization and configuration."""

    def test_default_initialization(self) -> None:
        """Test circuit breaker with default parameters."""
        breaker: CircuitBreaker = CircuitBreaker()

        assert breaker.failure_threshold == 5
        assert breaker.recovery_timeout == timedelta(seconds=60)
        assert breaker.success_threshold == 2
        assert breaker.expected_exception is Exception
        assert breaker.name == "circuit_breaker"
        assert breaker.service_name == "unknown"
        assert breaker.failure_count == 0
        assert breaker.success_count == 0
        assert breaker.last_failure_time is None
        assert breaker.state == CircuitBreakerState.CLOSED

    def test_custom_initialization(self, mock_metrics: Mock, test_tracer: Tracer) -> None:
        """Test circuit breaker with custom parameters."""
        breaker: CircuitBreaker = CircuitBreaker(
            failure_threshold=10,
            recovery_timeout=timedelta(seconds=120),
            success_threshold=3,
            expected_exception=ValueError,
            name="custom_breaker",
            tracer=test_tracer,
            metrics=mock_metrics,
            service_name="custom_service",
        )

        assert breaker.failure_threshold == 10
        assert breaker.recovery_timeout == timedelta(seconds=120)
        assert breaker.success_threshold == 3
        assert breaker.expected_exception is ValueError
        assert breaker.name == "custom_breaker"
        assert breaker.service_name == "custom_service"
        assert breaker._explicit_tracer == test_tracer
        assert breaker.metrics == mock_metrics

    def test_metrics_initialization(self, mock_metrics: Mock) -> None:
        """Test that metrics are initialized with current state."""
        CircuitBreaker(name="test_breaker", metrics=mock_metrics, service_name="test_service")

        # Verify metrics were called during initialization
        mock_metrics.set_state.assert_called_once_with(
            "test_breaker", CircuitBreakerState.CLOSED, "test_service"
        )


class TestCircuitBreakerTracer:
    """Test tracer property and lazy initialization."""

    def test_explicit_tracer_returned(self, test_tracer: Tracer) -> None:
        """Test that explicit tracer is returned when provided."""
        breaker = CircuitBreaker(tracer=test_tracer)

        assert breaker.tracer == test_tracer

    def test_lazy_tracer_initialization(self) -> None:
        """Test lazy tracer creation when none provided."""
        breaker: CircuitBreaker = CircuitBreaker()

        # First access should create tracer
        tracer1: Tracer = breaker.tracer
        assert tracer1 is not None

        # Second access should return same tracer
        tracer2: Tracer = breaker.tracer
        assert tracer2 == tracer1

    def test_lazy_tracer_caching(self) -> None:
        """Test that lazy tracer is cached properly."""
        breaker: CircuitBreaker = CircuitBreaker()

        # Access tracer multiple times
        tracers: list[Tracer] = [breaker.tracer for _ in range(5)]

        # All should be the same instance
        assert all(t == tracers[0] for t in tracers)


class TestCircuitBreakerStateTransitions:
    """Test circuit breaker state machine transitions."""

    @pytest.mark.asyncio
    async def test_closed_to_open_transition(self, test_circuit_breaker: CircuitBreaker) -> None:
        """Test transition from CLOSED to OPEN after threshold failures."""
        # Simulate failures up to threshold (3)
        for i in range(3):
            with pytest.raises(ValueError):
                await test_circuit_breaker.call(failing_async_function, f"failure_{i}")

            if i < 2:  # Not at threshold yet
                assert test_circuit_breaker.state == CircuitBreakerState.CLOSED
                assert test_circuit_breaker.failure_count == i + 1

        # Should now be OPEN
        assert test_circuit_breaker.state == CircuitBreakerState.OPEN
        assert test_circuit_breaker.failure_count == 3
        assert test_circuit_breaker.last_failure_time is not None

    @pytest.mark.asyncio
    async def test_open_to_half_open_transition(self, test_circuit_breaker: CircuitBreaker) -> None:
        """Test transition from OPEN to HALF_OPEN after recovery timeout."""
        # Force to OPEN state
        await self._force_open_state(test_circuit_breaker)

        # Wait for recovery timeout (1 second for test)
        await asyncio.sleep(1.1)

        # Next call should transition to HALF_OPEN
        result: str = await test_circuit_breaker.call(successful_async_function, "test")

        assert result == "success_test"
        assert test_circuit_breaker.state == CircuitBreakerState.HALF_OPEN
        assert test_circuit_breaker.success_count == 1

    @pytest.mark.asyncio
    async def test_half_open_to_closed_transition(
        self, test_circuit_breaker: CircuitBreaker
    ) -> None:
        """Test transition from HALF_OPEN to CLOSED after success threshold."""
        # Force to HALF_OPEN state
        await self._force_half_open_state(test_circuit_breaker)

        # Make successful calls to reach threshold (2)
        await test_circuit_breaker.call(successful_async_function, "test1")
        assert test_circuit_breaker.state == CircuitBreakerState.HALF_OPEN
        assert test_circuit_breaker.success_count == 1

        await test_circuit_breaker.call(successful_async_function, "test2")

        # Should now be CLOSED
        assert test_circuit_breaker.state == CircuitBreakerState.CLOSED
        assert test_circuit_breaker.success_count == 0
        assert test_circuit_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_failure(self, test_circuit_breaker: CircuitBreaker) -> None:
        """Test transition from HALF_OPEN back to OPEN on single failure."""
        # Force to HALF_OPEN state
        await self._force_half_open_state(test_circuit_breaker)

        # Single failure should return to OPEN
        with pytest.raises(ValueError):
            await test_circuit_breaker.call(failing_async_function, "failure")

        assert test_circuit_breaker.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_closed_state_failure_count_reset_on_success(
        self, test_circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that failure count resets on success in CLOSED state."""
        # Make some failures (but not enough to open)
        for i in range(2):
            with pytest.raises(ValueError):
                await test_circuit_breaker.call(failing_async_function, f"failure_{i}")

        assert test_circuit_breaker.failure_count == 2
        assert test_circuit_breaker.state == CircuitBreakerState.CLOSED

        # Successful call should reset failure count
        await test_circuit_breaker.call(successful_async_function, "success")

        assert test_circuit_breaker.failure_count == 0
        assert test_circuit_breaker.state == CircuitBreakerState.CLOSED

    async def _force_open_state(self, breaker: CircuitBreaker) -> None:
        """Helper to force circuit breaker to OPEN state."""
        for i in range(breaker.failure_threshold):
            with pytest.raises(ValueError):
                await breaker.call(failing_async_function, f"failure_{i}")

    async def _force_half_open_state(self, breaker: CircuitBreaker) -> None:
        """Helper to force circuit breaker to HALF_OPEN state."""
        await self._force_open_state(breaker)
        await asyncio.sleep(breaker.recovery_timeout.total_seconds() + 0.1)
        # Set state manually for testing (simulate _should_attempt_reset trigger)
        breaker.state = CircuitBreakerState.HALF_OPEN
        breaker.success_count = 0
        breaker.failure_count = 0


class TestCircuitBreakerCallExecution:
    """Test circuit breaker call method with various scenarios."""

    @pytest.mark.asyncio
    async def test_successful_async_call(self, test_circuit_breaker: CircuitBreaker) -> None:
        """Test successful async function call."""
        result: str = await test_circuit_breaker.call(successful_async_function, "test_value")

        assert result == "success_test_value"
        assert test_circuit_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_successful_sync_call(self, test_circuit_breaker: CircuitBreaker) -> None:
        """Test successful sync function call."""
        result: str = await test_circuit_breaker.call(successful_sync_function, "test_value")

        assert result == "success_test_value"
        assert test_circuit_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_expected_exception_handling(self, test_circuit_breaker: CircuitBreaker) -> None:
        """Test handling of expected exceptions."""
        with pytest.raises(ValueError, match="test_failure"):
            await test_circuit_breaker.call(failing_async_function, "test_failure")

        assert test_circuit_breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_unexpected_exception_passthrough(
        self, test_circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that unexpected exceptions pass through without counting as failures."""
        with pytest.raises(RuntimeError, match="Unexpected error"):
            await test_circuit_breaker.call(unexpected_error_function)

        # Should not count as failure since RuntimeError is not expected_exception (ValueError)
        assert test_circuit_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_open_circuit_blocks_calls(self, test_circuit_breaker: CircuitBreaker) -> None:
        """Test that OPEN circuit blocks calls with CircuitBreakerError."""
        # Force circuit to OPEN
        for i in range(3):
            with pytest.raises(ValueError):
                await test_circuit_breaker.call(failing_async_function, f"failure_{i}")

        assert test_circuit_breaker.state == CircuitBreakerState.OPEN

        # Next call should be blocked
        with pytest.raises(CircuitBreakerError, match="Circuit breaker 'test_breaker' is OPEN"):
            await test_circuit_breaker.call(successful_async_function, "blocked")

    @pytest.mark.asyncio
    async def test_metrics_integration_success(
        self, test_circuit_breaker: CircuitBreaker, mock_metrics: Mock
    ) -> None:
        """Test metrics recording for successful calls."""
        await test_circuit_breaker.call(successful_async_function, "test")

        mock_metrics.increment_calls.assert_called_with("test_breaker", "success", "test_service")

    @pytest.mark.asyncio
    async def test_metrics_integration_failure(
        self, test_circuit_breaker: CircuitBreaker, mock_metrics: Mock
    ) -> None:
        """Test metrics recording for failed calls."""
        with pytest.raises(ValueError):
            await test_circuit_breaker.call(failing_async_function, "test")

        mock_metrics.increment_calls.assert_called_with("test_breaker", "failure", "test_service")

    @pytest.mark.asyncio
    async def test_blocked_call_metrics(
        self, test_circuit_breaker: CircuitBreaker, mock_metrics: Mock
    ) -> None:
        """Test metrics recording for blocked calls."""
        # Force to OPEN state
        for i in range(3):
            with pytest.raises(ValueError):
                await test_circuit_breaker.call(failing_async_function, f"failure_{i}")

        # Clear previous calls
        mock_metrics.reset_mock()

        # Blocked call should record metrics
        with pytest.raises(CircuitBreakerError):
            await test_circuit_breaker.call(successful_async_function, "blocked")

        mock_metrics.record_blocked_call.assert_called_once_with("test_breaker", "test_service")


class TestCircuitBreakerUtilityMethods:
    """Test circuit breaker utility methods."""

    def test_get_state_method(self, test_circuit_breaker: CircuitBreaker) -> None:
        """Test get_state returns correct state information."""
        state: dict[str, Any] = test_circuit_breaker.get_state()

        expected_state: dict[str, Any] = {
            "name": "test_breaker",
            "state": "closed",
            "failure_count": 0,
            "success_count": 0,
            "last_failure_time": None,
        }

        assert state == expected_state

    @pytest.mark.asyncio
    async def test_get_state_with_failure_time(self, test_circuit_breaker: CircuitBreaker) -> None:
        """Test get_state includes failure time when present."""
        # Cause a failure to set last_failure_time
        with pytest.raises(ValueError):
            await test_circuit_breaker.call(failing_async_function, "test")

        state = test_circuit_breaker.get_state()

        assert state["last_failure_time"] is not None
        assert isinstance(state["last_failure_time"], str)  # Should be ISO format

    def test_reset_method(self, test_circuit_breaker: CircuitBreaker) -> None:
        """Test manual reset to CLOSED state."""
        # Manually set some state
        test_circuit_breaker.state = CircuitBreakerState.OPEN
        test_circuit_breaker.failure_count = 5
        test_circuit_breaker.success_count = 1
        test_circuit_breaker.last_failure_time = datetime.now(timezone.utc)

        # Reset should clear everything
        test_circuit_breaker.reset()

        assert test_circuit_breaker.state == CircuitBreakerState.CLOSED
        assert test_circuit_breaker.failure_count == 0
        assert test_circuit_breaker.success_count == 0
        assert test_circuit_breaker.last_failure_time is None

    def test_reset_records_metrics(
        self, test_circuit_breaker: CircuitBreaker, mock_metrics: Mock
    ) -> None:
        """Test that reset records state change metrics."""
        # Set to non-CLOSED state
        test_circuit_breaker.state = CircuitBreakerState.OPEN

        test_circuit_breaker.reset()

        mock_metrics.record_state_change.assert_called_with(
            "test_breaker", CircuitBreakerState.OPEN, CircuitBreakerState.CLOSED, "test_service"
        )

    def test_reset_no_metrics_when_already_closed(
        self, test_circuit_breaker: CircuitBreaker, mock_metrics: Mock
    ) -> None:
        """Test that reset doesn't record metrics when already CLOSED."""
        # Already CLOSED by default
        mock_metrics.reset_mock()  # Clear initialization call

        test_circuit_breaker.reset()

        # Should not record metrics since no state change occurred
        mock_metrics.record_state_change.assert_not_called()


class TestCircuitBreakerDecorator:
    """Test circuit_breaker decorator function."""

    @pytest.mark.asyncio
    async def test_decorator_async_function(self) -> None:
        """Test decorator with async function."""

        @circuit_breaker(failure_threshold=2, recovery_timeout=timedelta(seconds=0.1))
        async def decorated_async_func(value: str) -> str:
            if value == "fail":
                raise ValueError("Decorated failure")
            return f"decorated_{value}"

        # Test successful call
        result: str = await decorated_async_func("success")
        assert result == "decorated_success"

        # Test failure
        with pytest.raises(ValueError, match="Decorated failure"):
            await decorated_async_func("fail")

    def test_decorator_sync_function(self) -> None:
        """Test decorator with sync function."""

        @circuit_breaker(failure_threshold=2, recovery_timeout=timedelta(seconds=0.1))
        def decorated_sync_func(value: str) -> str:
            if value == "fail":
                raise ValueError("Decorated failure")
            return f"decorated_{value}"

        # Test successful call
        result: str = decorated_sync_func("success")
        assert result == "decorated_success"

        # Test failure
        with pytest.raises(ValueError, match="Decorated failure"):
            decorated_sync_func("fail")

    def test_decorator_name_generation(self) -> None:
        """Test that decorator generates appropriate names."""

        @circuit_breaker()
        def test_function() -> str:
            return "test"

        # Access the underlying circuit breaker (this is implementation detail for testing)
        # The decorator creates a closure, so we can't easily access the breaker name
        # This test verifies the decorator doesn't crash on name generation
        result: str = test_function()
        assert result == "test"

    @pytest.mark.asyncio
    async def test_decorator_circuit_opening(self) -> None:
        """Test that decorated function respects circuit breaker behavior."""

        @circuit_breaker(failure_threshold=2, recovery_timeout=timedelta(seconds=10))
        async def failing_decorated_func() -> str:
            raise ValueError("Always fails")

        # Cause failures to open circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                await failing_decorated_func()

        # Next call should be blocked by circuit breaker
        with pytest.raises(CircuitBreakerError):
            await failing_decorated_func()


class TestCircuitBreakerEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_access_thread_safety(
        self, test_circuit_breaker: CircuitBreaker
    ) -> None:
        """Test thread safety of circuit breaker with concurrent access."""

        async def make_call(call_id: int) -> str:
            if call_id % 2 == 0:
                return await test_circuit_breaker.call(successful_async_function, f"call_{call_id}")
            else:
                try:
                    return await test_circuit_breaker.call(
                        failing_async_function, f"fail_{call_id}"
                    )
                except ValueError:
                    return f"failed_{call_id}"

        # Make concurrent calls
        tasks: list[Any] = [make_call(i) for i in range(10)]
        results: list[Any] = await asyncio.gather(*tasks, return_exceptions=True)

        # Should not crash and should maintain consistent state
        assert len(results) == 10
        assert test_circuit_breaker.failure_count <= test_circuit_breaker.failure_threshold

    @pytest.mark.asyncio
    async def test_recovery_timeout_precision(self) -> None:
        """Test that recovery timeout is respected precisely."""
        breaker: CircuitBreaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=timedelta(milliseconds=100),
            expected_exception=ValueError,
        )

        # Force to OPEN
        with pytest.raises(ValueError):
            await breaker.call(failing_async_function, "failure")

        # Should still be blocked immediately
        with pytest.raises(CircuitBreakerError):
            await breaker.call(successful_async_function, "blocked")

        # Wait for recovery timeout
        await asyncio.sleep(0.15)  # 150ms > 100ms timeout

        # Should now allow call and transition to HALF_OPEN
        result: str = await breaker.call(successful_async_function, "recovered")
        assert result == "success_recovered"
        assert breaker.state == CircuitBreakerState.HALF_OPEN

    def test_zero_thresholds_handling(self) -> None:
        """Test circuit breaker behavior with edge case threshold values."""
        # Zero failure threshold should immediately open
        breaker_zero_failure: CircuitBreaker = CircuitBreaker(failure_threshold=0)
        assert breaker_zero_failure.state == CircuitBreakerState.CLOSED  # Starts closed

        # Zero success threshold should immediately close from half-open
        breaker_zero_success: CircuitBreaker = CircuitBreaker(success_threshold=0)
        assert breaker_zero_success.success_threshold == 0

    @pytest.mark.asyncio
    async def test_function_with_args_and_kwargs(
        self, test_circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that function arguments and keyword arguments are properly passed."""

        # Use sync function for this test to match circuit breaker type signature
        def function_with_args(pos_arg: str, keyword_arg: str = "default") -> str:
            return f"pos={pos_arg}, kw={keyword_arg}"

        result: str = await test_circuit_breaker.call(
            function_with_args, "positional", keyword_arg="keyword"
        )

        assert result == "pos=positional, kw=keyword"
