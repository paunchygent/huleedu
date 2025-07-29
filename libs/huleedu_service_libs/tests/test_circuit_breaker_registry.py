"""
Unit tests for CircuitBreakerRegistry infrastructure.

Tests comprehensive registry functionality including registration, retrieval,
state management, and logging integration. Follows HuleEdu testing excellence
patterns with complete coverage and proper type safety.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker
from huleedu_service_libs.resilience.registry import CircuitBreakerRegistry


# Test fixtures
@pytest.fixture
def registry() -> CircuitBreakerRegistry:
    """Provide fresh registry for each test."""
    return CircuitBreakerRegistry()


@pytest.fixture
def test_circuit_breaker() -> CircuitBreaker:
    """Provide test circuit breaker with standard configuration."""
    return CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=timedelta(seconds=60),
        success_threshold=2,
        expected_exception=ValueError,
        name="test_breaker",
        service_name="test_service",
    )


@pytest.fixture
def secondary_circuit_breaker() -> CircuitBreaker:
    """Provide second circuit breaker for multi-breaker tests."""
    return CircuitBreaker(
        failure_threshold=5,
        recovery_timeout=timedelta(seconds=30),
        success_threshold=1,
        expected_exception=ConnectionError,
        name="secondary_breaker",
        service_name="secondary_service",
    )


class TestCircuitBreakerRegistryConstruction:
    """Test registry construction and initialization."""

    def test_registry_initialization(self, registry: CircuitBreakerRegistry) -> None:
        """Test CircuitBreakerRegistry initialization."""
        # Verify registry starts empty
        assert len(registry) == 0
        assert isinstance(registry._breakers, dict)
        assert len(registry._breakers) == 0

    @patch("huleedu_service_libs.resilience.registry.logger")
    def test_registry_initialization_logging(self, mock_logger: MagicMock) -> None:
        """Test initialization logging."""
        # Create registry after mock is in place
        CircuitBreakerRegistry()
        mock_logger.info.assert_called_with("CircuitBreakerRegistry initialized")

    def test_registry_empty_state_operations(self, registry: CircuitBreakerRegistry) -> None:
        """Test operations on empty registry."""
        # Empty registry should handle operations gracefully
        assert registry.get("nonexistent") is None
        assert registry.get_all_states() == {}
        assert len(registry) == 0

        # Reset on empty registry should not crash
        registry.reset_all()
        assert len(registry) == 0


class TestCircuitBreakerRegistration:
    """Test circuit breaker registration functionality."""

    @patch("huleedu_service_libs.resilience.registry.logger")
    def test_register_single_circuit_breaker(
        self,
        mock_logger: MagicMock,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test registering a single circuit breaker."""
        registry.register("test_cb", test_circuit_breaker)

        # Verify registration
        assert len(registry) == 1
        assert registry.get("test_cb") is test_circuit_breaker

        # Verify logging
        mock_logger.info.assert_called_with("Registered circuit breaker: test_cb")

    def test_register_multiple_circuit_breakers(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
        secondary_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test registering multiple circuit breakers."""
        registry.register("first", test_circuit_breaker)
        registry.register("second", secondary_circuit_breaker)

        # Verify both registered
        assert len(registry) == 2
        assert registry.get("first") is test_circuit_breaker
        assert registry.get("second") is secondary_circuit_breaker

    @patch("huleedu_service_libs.resilience.registry.logger")
    def test_register_overwrite_existing(
        self,
        mock_logger: MagicMock,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
        secondary_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test registering with same name overwrites existing."""
        # Register first circuit breaker
        registry.register("duplicate_name", test_circuit_breaker)
        assert registry.get("duplicate_name") is test_circuit_breaker

        # Register second with same name
        registry.register("duplicate_name", secondary_circuit_breaker)

        # Verify overwrite occurred
        assert len(registry) == 1  # Still only one entry
        assert registry.get("duplicate_name") is secondary_circuit_breaker
        assert registry.get("duplicate_name") is not test_circuit_breaker

        # Verify warning was logged
        mock_logger.warning.assert_called_with(
            "Overwriting existing circuit breaker: duplicate_name"
        )

    def test_register_with_different_configurations(self, registry: CircuitBreakerRegistry) -> None:
        """Test registering circuit breakers with different configurations."""
        # Create circuit breakers with different configurations
        fast_recovery = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=timedelta(seconds=5),
            name="fast_recovery",
        )

        slow_recovery = CircuitBreaker(
            failure_threshold=10,
            recovery_timeout=timedelta(minutes=5),
            name="slow_recovery",
        )

        # Register both
        registry.register("fast", fast_recovery)
        registry.register("slow", slow_recovery)

        # Verify configurations preserved
        assert len(registry) == 2
        retrieved_fast = registry.get("fast")
        retrieved_slow = registry.get("slow")

        assert retrieved_fast is not None
        assert retrieved_slow is not None
        assert retrieved_fast.failure_threshold == 1
        assert retrieved_slow.failure_threshold == 10


class TestCircuitBreakerRetrieval:
    """Test circuit breaker retrieval functionality."""

    def test_get_existing_circuit_breaker(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test retrieving existing circuit breaker."""
        registry.register("existing", test_circuit_breaker)

        retrieved = registry.get("existing")
        assert retrieved is test_circuit_breaker
        assert retrieved is not None

    def test_get_nonexistent_circuit_breaker(self, registry: CircuitBreakerRegistry) -> None:
        """Test retrieving nonexistent circuit breaker returns None."""
        result = registry.get("nonexistent")
        assert result is None

    def test_get_from_empty_registry(self, registry: CircuitBreakerRegistry) -> None:
        """Test retrieval from empty registry."""
        assert len(registry) == 0
        result = registry.get("anything")
        assert result is None

    def test_get_after_multiple_registrations(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
        secondary_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test retrieval after multiple registrations."""
        registry.register("first", test_circuit_breaker)
        registry.register("second", secondary_circuit_breaker)
        registry.register("third", test_circuit_breaker)  # Reuse first breaker

        # Verify each can be retrieved correctly
        assert registry.get("first") is test_circuit_breaker
        assert registry.get("second") is secondary_circuit_breaker
        assert registry.get("third") is test_circuit_breaker
        assert registry.get("fourth") is None

    def test_get_case_sensitive_names(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test that circuit breaker names are case sensitive."""
        registry.register("TestBreaker", test_circuit_breaker)

        # Case sensitive - these should not match
        assert registry.get("TestBreaker") is test_circuit_breaker
        assert registry.get("testbreaker") is None
        assert registry.get("TESTBREAKER") is None
        assert registry.get("testBreaker") is None


class TestRegistryStateManagement:
    """Test registry state management functionality."""

    def test_get_all_states_empty_registry(self, registry: CircuitBreakerRegistry) -> None:
        """Test getting all states from empty registry."""
        states = registry.get_all_states()
        assert states == {}
        assert isinstance(states, dict)

    def test_get_all_states_single_breaker(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test getting all states with single circuit breaker."""
        registry.register("single", test_circuit_breaker)

        states = registry.get_all_states()
        assert len(states) == 1
        assert "single" in states

        # Verify state structure
        single_state = states["single"]
        assert isinstance(single_state, dict)
        assert "name" in single_state
        assert "state" in single_state
        assert "failure_count" in single_state
        assert single_state["name"] == "test_breaker"
        assert single_state["state"] == "closed"

    def test_get_all_states_multiple_breakers(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
        secondary_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test getting all states with multiple circuit breakers."""
        registry.register("primary", test_circuit_breaker)
        registry.register("secondary", secondary_circuit_breaker)

        states = registry.get_all_states()
        assert len(states) == 2
        assert "primary" in states
        assert "secondary" in states

        # Verify both states are present and different
        primary_state = states["primary"]
        secondary_state = states["secondary"]
        assert primary_state["name"] == "test_breaker"
        assert secondary_state["name"] == "secondary_breaker"

    def test_reset_all_empty_registry(self, registry: CircuitBreakerRegistry) -> None:
        """Test reset_all on empty registry."""
        registry.reset_all()

        # Should not crash
        assert len(registry) == 0

    @patch("huleedu_service_libs.resilience.registry.logger")
    def test_reset_all_single_breaker(
        self,
        mock_logger: MagicMock,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test reset_all with single circuit breaker."""
        registry.register("resettable", test_circuit_breaker)

        # Modify circuit breaker state
        test_circuit_breaker.failure_count = 2

        # Reset all
        registry.reset_all()

        # Verify reset occurred
        assert test_circuit_breaker.failure_count == 0
        mock_logger.info.assert_called_with("Reset circuit breaker: resettable")

    @patch("huleedu_service_libs.resilience.registry.logger")
    def test_reset_all_multiple_breakers(
        self,
        mock_logger: MagicMock,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
        secondary_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test reset_all with multiple circuit breakers."""
        registry.register("first", test_circuit_breaker)
        registry.register("second", secondary_circuit_breaker)

        # Modify both circuit breaker states
        test_circuit_breaker.failure_count = 3
        secondary_circuit_breaker.failure_count = 1

        # Reset all
        registry.reset_all()

        # Verify both were reset
        assert test_circuit_breaker.failure_count == 0
        assert secondary_circuit_breaker.failure_count == 0

        # Verify logging for both breakers (check last few calls)
        all_log_calls = [str(call) for call in mock_logger.info.call_args_list]
        reset_calls = [call for call in all_log_calls if "Reset circuit breaker:" in call]

        # Should have logged reset for both breakers
        assert len(reset_calls) >= 2
        assert any("Reset circuit breaker: first" in call for call in reset_calls)
        assert any("Reset circuit breaker: second" in call for call in reset_calls)


class TestRegistryUtilityMethods:
    """Test registry utility methods."""

    def test_len_empty_registry(self, registry: CircuitBreakerRegistry) -> None:
        """Test length of empty registry."""
        assert len(registry) == 0

    def test_len_single_registration(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test length after single registration."""
        registry.register("single", test_circuit_breaker)
        assert len(registry) == 1

    def test_len_multiple_registrations(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
        secondary_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test length after multiple registrations."""
        registry.register("first", test_circuit_breaker)
        assert len(registry) == 1

        registry.register("second", secondary_circuit_breaker)
        assert len(registry) == 2

        registry.register("third", test_circuit_breaker)  # Reuse existing breaker
        assert len(registry) == 3

    def test_len_after_overwrite(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
        secondary_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test length after overwriting existing registration."""
        registry.register("name", test_circuit_breaker)
        assert len(registry) == 1

        # Overwrite with different breaker
        registry.register("name", secondary_circuit_breaker)
        assert len(registry) == 1  # Should still be 1, not 2


class TestRegistryEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_register_with_empty_string_name(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test registration with empty string name."""
        registry.register("", test_circuit_breaker)

        assert len(registry) == 1
        assert registry.get("") is test_circuit_breaker
        assert registry.get("anything_else") is None

    def test_register_with_special_character_names(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test registration with special character names."""
        special_names = [
            "name-with-dashes",
            "name_with_underscores",
            "name.with.dots",
            "name with spaces",
            "name/with/slashes",
            "name:with:colons",
        ]

        for name in special_names:
            registry.register(name, test_circuit_breaker)

        # Verify all can be retrieved
        assert len(registry) == len(special_names)
        for name in special_names:
            assert registry.get(name) is test_circuit_breaker

    def test_very_long_circuit_breaker_name(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test registration with very long name."""
        long_name = "a" * 1000  # 1000 character name

        registry.register(long_name, test_circuit_breaker)
        assert registry.get(long_name) is test_circuit_breaker
        assert len(registry) == 1

    def test_unicode_circuit_breaker_names(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test registration with Unicode names."""
        unicode_names = [
            "测试断路器",  # Chinese
            "тест_автомат",  # Russian
            "circuit_breaker_🔧",  # Emoji
            "café_müncher",  # Accented characters
        ]

        for name in unicode_names:
            registry.register(name, test_circuit_breaker)

        # Verify all can be retrieved
        assert len(registry) == len(unicode_names)
        for name in unicode_names:
            assert registry.get(name) is test_circuit_breaker

    def test_numeric_string_names(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test registration with numeric string names."""
        numeric_names = ["0", "123", "-456", "3.14159", "1e10"]

        for name in numeric_names:
            registry.register(name, test_circuit_breaker)

        # Verify all can be retrieved
        assert len(registry) == len(numeric_names)
        for name in numeric_names:
            assert registry.get(name) is test_circuit_breaker


class TestRegistryIntegrationScenarios:
    """Test integration scenarios combining multiple operations."""

    def test_full_lifecycle_operations(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
        secondary_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test complete lifecycle of registry operations."""
        # Start empty
        assert len(registry) == 0
        assert registry.get_all_states() == {}

        # Register first breaker
        registry.register("primary", test_circuit_breaker)
        assert len(registry) == 1
        states = registry.get_all_states()
        assert len(states) == 1
        assert "primary" in states

        # Register second breaker
        registry.register("secondary", secondary_circuit_breaker)
        assert len(registry) == 2

        # Overwrite first breaker
        registry.register("primary", secondary_circuit_breaker)
        assert len(registry) == 2  # Still 2, not 3

        # Get all states
        final_states = registry.get_all_states()
        assert len(final_states) == 2
        assert final_states["primary"]["name"] == "secondary_breaker"
        assert final_states["secondary"]["name"] == "secondary_breaker"

        # Reset all
        registry.reset_all()
        assert len(registry) == 2  # Breakers still registered

        # Verify states after reset
        reset_states = registry.get_all_states()
        assert all(state["failure_count"] == 0 for state in reset_states.values())

    def test_concurrent_access_patterns(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test patterns that might occur with concurrent access."""
        # Register same circuit breaker with multiple names
        names = [f"cb_{i}" for i in range(10)]

        for name in names:
            registry.register(name, test_circuit_breaker)

        # Verify all point to same instance
        assert len(registry) == 10
        for name in names:
            assert registry.get(name) is test_circuit_breaker

        # Get all states should show same underlying breaker data
        states = registry.get_all_states()
        assert len(states) == 10

        # All should have same breaker name since they're the same instance
        breaker_names = {state["name"] for state in states.values()}
        assert len(breaker_names) == 1  # All should be the same
        assert "test_breaker" in breaker_names

    def test_registry_state_consistency(
        self,
        registry: CircuitBreakerRegistry,
        test_circuit_breaker: CircuitBreaker,
        secondary_circuit_breaker: CircuitBreaker,
    ) -> None:
        """Test that registry maintains consistent state across operations."""
        # Register breakers
        registry.register("cb1", test_circuit_breaker)
        registry.register("cb2", secondary_circuit_breaker)

        # Modify one breaker's state
        test_circuit_breaker.failure_count = 5

        # Verify states reflect the change
        states = registry.get_all_states()
        assert states["cb1"]["failure_count"] == 5
        assert states["cb2"]["failure_count"] == 0

        # Reset one specific breaker directly
        test_circuit_breaker.reset()

        # Verify registry reflects the change
        updated_states = registry.get_all_states()
        assert updated_states["cb1"]["failure_count"] == 0
        assert updated_states["cb2"]["failure_count"] == 0
