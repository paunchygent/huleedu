"""
Unit tests for ResilientClientWrapper infrastructure.

Tests circuit breaker wrapper functionality focusing on async methods and core
wrapper behavior. Avoids sync method testing due to event loop conflicts.
Follows HuleEdu testing excellence patterns with proper type safety.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker
from huleedu_service_libs.resilience.resilient_client import (
    ResilientClientWrapper,
    make_resilient,
)


class MockAsyncService:
    """Real async service implementation for testing wrapper behavior."""

    def __init__(self) -> None:
        self.call_history: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.status = "ready"
        self.should_fail = False

    async def async_operation(self, data: str) -> str:
        """Test async operation."""
        self.call_history.append(("async_operation", (data,), {}))
        if self.should_fail:
            raise ValueError(f"Async operation failed for {data}")
        return f"async_processed_{data}"

    async def async_with_kwargs(self, data: str, option: str = "default") -> str:
        """Test async operation with keyword arguments."""
        self.call_history.append(("async_with_kwargs", (data,), {"option": option}))
        return f"async_{data}_{option}"

    async def async_none_method(self) -> None:
        """Test async operation returning None."""
        self.call_history.append(("async_none_method", (), {}))
        return None

    def get_status(self) -> str:
        """Get current status (non-callable property)."""
        return self.status

    def reset(self) -> None:
        """Reset test service state."""
        self.call_history.clear()
        self.status = "ready"
        self.should_fail = False


# Test fixtures
@pytest.fixture
def mock_service() -> MockAsyncService:
    """Provide mock service for testing."""
    return MockAsyncService()


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """Provide circuit breaker with test configuration."""
    return CircuitBreaker(
        failure_threshold=2,
        success_threshold=1,
        expected_exception=ValueError,
        name="test_circuit",
    )


@pytest.fixture
def service_and_wrapper(
    mock_service: MockAsyncService, circuit_breaker: CircuitBreaker
) -> tuple[MockAsyncService, ResilientClientWrapper]:
    """Provide both service and wrapper for testing."""
    wrapper = ResilientClientWrapper(mock_service, circuit_breaker)
    return mock_service, wrapper


class TestResilientClientWrapperConstruction:
    """Test wrapper construction and basic functionality."""

    def test_wrapper_initialization(
        self, mock_service: MockAsyncService, circuit_breaker: CircuitBreaker
    ) -> None:
        """Test ResilientClientWrapper initialization."""
        wrapper = ResilientClientWrapper(mock_service, circuit_breaker)

        # Verify wrapper has expected structure
        assert hasattr(wrapper, "_delegate")
        assert hasattr(wrapper, "_circuit_breaker")
        assert hasattr(wrapper, "_wrapped_methods")

    def test_wrapper_repr(
        self, mock_service: MockAsyncService, circuit_breaker: CircuitBreaker
    ) -> None:
        """Test wrapper string representation."""
        wrapper = ResilientClientWrapper(mock_service, circuit_breaker)
        repr_str = repr(wrapper)

        assert "ResilientClientWrapper(MockAsyncService)" in repr_str

    def test_non_callable_attribute_passthrough(
        self, service_and_wrapper: tuple[MockAsyncService, ResilientClientWrapper]
    ) -> None:
        """Test that non-callable attributes pass through directly."""
        mock_service, wrapper = service_and_wrapper

        # Access property-like attribute
        assert wrapper.status == "ready"  # type: ignore[attr-defined]

        # Modify the service and verify passthrough
        mock_service.status = "modified"
        assert wrapper.status == "modified"  # type: ignore[attr-defined]


class TestAsyncMethodWrapping:
    """Test async method wrapping through circuit breaker."""

    @pytest.mark.asyncio
    async def test_async_method_success(
        self, service_and_wrapper: tuple[MockAsyncService, ResilientClientWrapper]
    ) -> None:
        """Test successful async method call."""
        mock_service, wrapper = service_and_wrapper

        result = await wrapper.async_operation("test_data")  # type: ignore[attr-defined]

        assert result == "async_processed_test_data"
        assert len(mock_service.call_history) == 1
        assert mock_service.call_history[0] == ("async_operation", ("test_data",), {})

    @pytest.mark.asyncio
    async def test_async_method_with_kwargs(
        self, service_and_wrapper: tuple[MockAsyncService, ResilientClientWrapper]
    ) -> None:
        """Test async method with keyword arguments."""
        mock_service, wrapper = service_and_wrapper

        result = await wrapper.async_with_kwargs("data", option="custom")  # type: ignore[attr-defined]

        assert result == "async_data_custom"
        assert len(mock_service.call_history) == 1
        assert mock_service.call_history[0] == (
            "async_with_kwargs",
            ("data",),
            {"option": "custom"},
        )

    @pytest.mark.asyncio
    async def test_async_method_with_none_return(
        self, service_and_wrapper: tuple[MockAsyncService, ResilientClientWrapper]
    ) -> None:
        """Test async method that returns None."""
        mock_service, wrapper = service_and_wrapper

        result = await wrapper.async_none_method()  # type: ignore[attr-defined]

        assert result is None
        assert len(mock_service.call_history) == 1
        assert mock_service.call_history[0] == ("async_none_method", (), {})

    @pytest.mark.asyncio
    async def test_async_method_failure_handling(
        self, service_and_wrapper: tuple[MockAsyncService, ResilientClientWrapper]
    ) -> None:
        """Test async method failure propagation."""
        mock_service, wrapper = service_and_wrapper
        mock_service.should_fail = True

        with pytest.raises(ValueError, match="Async operation failed for test_data"):
            await wrapper.async_operation("test_data")  # type: ignore[attr-defined]

        assert len(mock_service.call_history) == 1

    @pytest.mark.asyncio
    async def test_async_method_circuit_breaker_integration(
        self, service_and_wrapper: tuple[MockAsyncService, ResilientClientWrapper]
    ) -> None:
        """Test circuit breaker behavior with async methods."""
        mock_service, wrapper = service_and_wrapper

        # Successful call first
        result = await wrapper.async_operation("success")  # type: ignore[attr-defined]
        assert result == "async_processed_success"

        # Enable failures and trigger circuit breaker
        mock_service.should_fail = True

        # Two failures to open circuit (threshold = 2)
        for i in range(2):
            with pytest.raises(ValueError):
                await wrapper.async_operation(f"fail_{i}")  # type: ignore[attr-defined]

        # Verify circuit is open by attempting blocked call
        from huleedu_service_libs.resilience.circuit_breaker import CircuitBreakerError

        # Next call should be blocked
        with pytest.raises(CircuitBreakerError):
            await wrapper.async_operation("blocked")  # type: ignore[attr-defined]

        # Verify blocked call didn't reach service (3 calls: 1 success + 2 failures)
        assert len(mock_service.call_history) == 3


class TestMakeResilientFactory:
    """Test make_resilient factory function."""

    def test_make_resilient_creates_wrapper(
        self, mock_service: MockAsyncService, circuit_breaker: CircuitBreaker
    ) -> None:
        """Test make_resilient factory function."""
        resilient_service = make_resilient(mock_service, circuit_breaker)

        # Should return ResilientClientWrapper
        assert isinstance(resilient_service, ResilientClientWrapper)

        # Should maintain interface compatibility
        assert hasattr(resilient_service, "async_operation")
        assert hasattr(resilient_service, "async_with_kwargs")
        assert hasattr(resilient_service, "get_status")

    @pytest.mark.asyncio
    async def test_make_resilient_preserves_async_functionality(
        self, mock_service: MockAsyncService, circuit_breaker: CircuitBreaker
    ) -> None:
        """Test make_resilient preserves async functionality."""
        resilient_service = make_resilient(mock_service, circuit_breaker)

        # Test async method
        async_result = await resilient_service.async_operation("async_test")  # type: ignore[attr-defined]
        assert async_result == "async_processed_async_test"

        # Verify service received call
        assert len(mock_service.call_history) == 1


class TestResilientClientEdgeCases:
    """Test edge cases and error conditions."""

    def test_attribute_error_for_missing_methods(
        self, service_and_wrapper: tuple[MockAsyncService, ResilientClientWrapper]
    ) -> None:
        """Test AttributeError for non-existent methods."""
        _, wrapper = service_and_wrapper

        with pytest.raises(AttributeError):
            _ = wrapper.nonexistent_method  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_concurrent_async_calls(
        self, service_and_wrapper: tuple[MockAsyncService, ResilientClientWrapper]
    ) -> None:
        """Test concurrent async method calls."""
        mock_service, wrapper = service_and_wrapper

        # Make concurrent calls
        tasks = [
            wrapper.async_operation(f"concurrent_{i}")  # type: ignore[attr-defined]
            for i in range(3)
        ]

        results = await asyncio.gather(*tasks)

        # Verify all results
        expected = [f"async_processed_concurrent_{i}" for i in range(3)]
        assert results == expected

        # Verify all calls reached service
        assert len(mock_service.call_history) == 3

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure_patterns(
        self, service_and_wrapper: tuple[MockAsyncService, ResilientClientWrapper]
    ) -> None:
        """Test mixed success/failure patterns with circuit breaker."""
        mock_service, wrapper = service_and_wrapper

        # Success
        result1 = await wrapper.async_operation("success1")  # type: ignore[attr-defined]
        assert result1 == "async_processed_success1"

        # Failure
        mock_service.should_fail = True
        with pytest.raises(ValueError):
            await wrapper.async_operation("fail1")  # type: ignore[attr-defined]

        # Success again (should reset failure count in CLOSED circuit)
        mock_service.should_fail = False
        result2 = await wrapper.async_operation("success2")  # type: ignore[attr-defined]
        assert result2 == "async_processed_success2"

        # Verify calls
        assert len(mock_service.call_history) == 3
        call_methods = [call[0] for call in mock_service.call_history]
        assert call_methods == ["async_operation", "async_operation", "async_operation"]

    def test_method_caching_behavior(
        self, service_and_wrapper: tuple[MockAsyncService, ResilientClientWrapper]
    ) -> None:
        """Test that methods are cached after first access."""
        _, wrapper = service_and_wrapper

        # Initially no methods cached
        assert len(wrapper._wrapped_methods) == 0

        # Access method (doesn't call it, just accesses)
        method = getattr(wrapper, "async_operation")
        assert callable(method)

        # Should now be cached
        assert len(wrapper._wrapped_methods) == 1
        assert "async_operation" in wrapper._wrapped_methods


class TestCircuitBreakerIntegration:
    """Test integration with circuit breaker behavior."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_state_transitions(self, mock_service: MockAsyncService) -> None:
        """Test full circuit breaker state cycle."""
        # Create circuit breaker with specific parameters for testing
        circuit_breaker = CircuitBreaker(
            failure_threshold=2,
            success_threshold=1,
            expected_exception=ValueError,
            name="integration_test",
        )

        wrapper = ResilientClientWrapper(mock_service, circuit_breaker)

        from common_core import CircuitBreakerState
        from huleedu_service_libs.resilience.circuit_breaker import CircuitBreakerError

        # Initial state should be CLOSED
        assert circuit_breaker.state == CircuitBreakerState.CLOSED

        # Successful call
        result = await wrapper.async_operation("success")  # type: ignore[attr-defined]
        assert result == "async_processed_success"
        assert circuit_breaker.state == CircuitBreakerState.CLOSED

        # Two failures to open circuit
        mock_service.should_fail = True
        for i in range(2):
            with pytest.raises(ValueError):
                await wrapper.async_operation(f"fail_{i}")  # type: ignore[attr-defined]

        # Circuit should be OPEN
        assert circuit_breaker.state == CircuitBreakerState.OPEN

        # Next call should be blocked
        with pytest.raises(CircuitBreakerError):
            await wrapper.async_operation("blocked")  # type: ignore[attr-defined]

        # Verify service call history
        # (3 calls: 1 success + 2 failures, blocked doesn't reach service)
        assert len(mock_service.call_history) == 3

    def test_multiple_independent_circuit_breakers(self) -> None:
        """Test that different wrappers have independent circuit breakers."""
        service1 = MockAsyncService()
        service2 = MockAsyncService()

        circuit1 = CircuitBreaker(
            failure_threshold=1, expected_exception=ValueError, name="circuit1"
        )
        circuit2 = CircuitBreaker(
            failure_threshold=2, expected_exception=ValueError, name="circuit2"
        )

        wrapper1 = ResilientClientWrapper(service1, circuit1)
        wrapper2 = ResilientClientWrapper(service2, circuit2)

        from common_core import CircuitBreakerState

        # Both circuits start CLOSED
        assert circuit1.state == CircuitBreakerState.CLOSED
        assert circuit2.state == CircuitBreakerState.CLOSED

        # Different services should be independent
        assert wrapper1 is not wrapper2
        assert circuit1 is not circuit2

        # Verify they have different configurations
        assert circuit1.failure_threshold == 1
        assert circuit2.failure_threshold == 2


class TestWrapperInterfacePreservation:
    """Test that wrapper preserves original interface."""

    def test_wrapper_maintains_callable_interface(
        self, mock_service: MockAsyncService, circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that wrapper maintains callable interface."""
        wrapper = make_resilient(mock_service, circuit_breaker)

        # Should be usable as original service
        assert isinstance(wrapper, ResilientClientWrapper)

        # Should have required methods
        assert hasattr(wrapper, "async_operation")
        assert hasattr(wrapper, "async_with_kwargs")
        assert hasattr(wrapper, "get_status")

        # Methods should be callable
        assert callable(getattr(wrapper, "async_operation"))
        assert callable(getattr(wrapper, "async_with_kwargs"))

    @pytest.mark.asyncio
    async def test_method_signatures_preserved(
        self, mock_service: MockAsyncService, circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that method signatures work as expected."""
        wrapper = make_resilient(mock_service, circuit_breaker)

        # Test async method with proper signature
        result = await wrapper.async_operation("test")  # type: ignore[attr-defined]
        assert isinstance(result, str)
        assert result == "async_processed_test"

        # Test method with kwargs
        result_with_kwargs = await wrapper.async_with_kwargs("data", option="custom")  # type: ignore[attr-defined]
        assert isinstance(result_with_kwargs, str)
        assert result_with_kwargs == "async_data_custom"


class TestWrapperAttributeHandling:
    """Test wrapper attribute access patterns."""

    def test_property_access_without_caching(
        self, service_and_wrapper: tuple[MockAsyncService, ResilientClientWrapper]
    ) -> None:
        """Test that non-callable properties don't get cached."""
        mock_service, wrapper = service_and_wrapper

        # Access property
        status = wrapper.status  # type: ignore[attr-defined]
        assert status == "ready"

        # Should not be cached (only callable methods are cached)
        assert "status" not in wrapper._wrapped_methods

        # Change property and verify it reflects changes
        mock_service.status = "changed"
        new_status = wrapper.status  # type: ignore[attr-defined]
        assert new_status == "changed"

    def test_method_access_with_caching(
        self, service_and_wrapper: tuple[MockAsyncService, ResilientClientWrapper]
    ) -> None:
        """Test that callable methods get cached appropriately."""
        _, wrapper = service_and_wrapper

        # Access method twice
        method1 = getattr(wrapper, "async_operation")
        method2 = getattr(wrapper, "async_operation")

        # Should be the same cached instance
        assert method1 is method2

        # Should be in cache
        assert "async_operation" in wrapper._wrapped_methods
        assert wrapper._wrapped_methods["async_operation"] is method1
