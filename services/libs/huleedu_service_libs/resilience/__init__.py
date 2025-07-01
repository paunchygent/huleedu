"""Resilience patterns for HuleEdu services."""

from huleedu_service_libs.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    circuit_breaker,
)
from huleedu_service_libs.resilience.registry import CircuitBreakerRegistry

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitState",
    "circuit_breaker",
    "CircuitBreakerRegistry",
]
