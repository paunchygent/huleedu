"""Resilience patterns for HuleEdu services."""

from common_core import CircuitBreakerState

from huleedu_service_libs.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    circuit_breaker,
)
from huleedu_service_libs.resilience.registry import CircuitBreakerRegistry

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitBreakerState",
    "circuit_breaker",
    "CircuitBreakerRegistry",
]
