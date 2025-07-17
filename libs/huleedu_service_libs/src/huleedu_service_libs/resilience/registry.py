"""
Circuit Breaker Registry for centralized management.

This module provides a registry to manage multiple circuit breakers
across services with consistent configuration and monitoring.
"""

from typing import Any, Dict, Optional

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker

logger = create_service_logger("circuit_breaker_registry")


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        logger.info("CircuitBreakerRegistry initialized")

    def register(self, name: str, circuit_breaker: CircuitBreaker) -> None:
        """Register a circuit breaker with a unique name."""
        if name in self._breakers:
            logger.warning(f"Overwriting existing circuit breaker: {name}")

        self._breakers[name] = circuit_breaker
        logger.info(f"Registered circuit breaker: {name}")

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name."""
        return self._breakers.get(name)

    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Get current state of all circuit breakers."""
        return {name: breaker.get_state() for name, breaker in self._breakers.items()}

    def reset_all(self) -> None:
        """Reset all circuit breakers to closed state."""
        for name, breaker in self._breakers.items():
            breaker.reset()
            logger.info(f"Reset circuit breaker: {name}")

    def __len__(self) -> int:
        """Get number of registered circuit breakers."""
        return len(self._breakers)
