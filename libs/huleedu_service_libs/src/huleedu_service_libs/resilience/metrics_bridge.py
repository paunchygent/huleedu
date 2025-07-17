"""
Circuit Breaker Metrics Bridge for Prometheus integration.

This module provides a standardized interface for circuit breaker metrics
that can be integrated with any Prometheus metrics implementation.
"""

from __future__ import annotations

from typing import Any, Dict, Protocol

from common_core import CircuitBreakerState

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("circuit_breaker_metrics")


class CircuitBreakerMetrics(Protocol):
    """Protocol for circuit breaker metrics integration."""

    def record_state_change(
        self,
        circuit_name: str,
        from_state: CircuitBreakerState,
        to_state: CircuitBreakerState,
        service_name: str,
    ) -> None:
        """Record a circuit breaker state change."""
        ...

    def set_state(
        self,
        circuit_name: str,
        state: CircuitBreakerState,
        service_name: str,
    ) -> None:
        """Set the current circuit breaker state."""
        ...

    def increment_calls(
        self,
        circuit_name: str,
        result: str,
        service_name: str,
    ) -> None:
        """Increment circuit breaker call counter."""
        ...

    def record_blocked_call(
        self,
        circuit_name: str,
        service_name: str,
    ) -> None:
        """Record a blocked call due to open circuit."""
        ...


class StateMapper:
    """Maps circuit breaker states to numeric values for Prometheus."""

    STATE_TO_NUMERIC = {
        CircuitBreakerState.CLOSED: 0,
        CircuitBreakerState.OPEN: 1,
        CircuitBreakerState.HALF_OPEN: 2,
    }

    @classmethod
    def to_numeric(cls, state: CircuitBreakerState) -> int:
        """Convert circuit breaker state to numeric value."""
        return cls.STATE_TO_NUMERIC[state]

    @classmethod
    def to_string(cls, state: CircuitBreakerState) -> str:
        """Convert circuit breaker state to string value."""
        value = state.value
        # Runtime validation for type safety
        if not isinstance(value, str):
            raise TypeError(f"Expected CircuitBreakerState.value to be str, got: {type(value)}")
        return value


class PrometheusCircuitBreakerMetrics:
    """Prometheus implementation of circuit breaker metrics."""

    def __init__(self, metrics_dict: Dict[str, Any], service_name: str):
        """
        Initialize with Prometheus metrics dictionary.

        Args:
            metrics_dict: Dictionary containing Prometheus metrics instances
            service_name: Name of the service for labeling
        """
        self.metrics = metrics_dict
        self.service_name = service_name
        self.state_mapper = StateMapper()

        # Validate required metrics are present
        required_metrics = [
            "circuit_breaker_state",
            "circuit_breaker_state_changes",
            "circuit_breaker_calls_total",
        ]

        for metric_name in required_metrics:
            if metric_name not in self.metrics:
                logger.warning(f"Missing circuit breaker metric: {metric_name}")

    def record_state_change(
        self,
        circuit_name: str,
        from_state: CircuitBreakerState,
        to_state: CircuitBreakerState,
        service_name: str,
    ) -> None:
        """Record a circuit breaker state change."""
        try:
            # Update state gauge
            if "circuit_breaker_state" in self.metrics:
                numeric_state = self.state_mapper.to_numeric(to_state)
                self.metrics["circuit_breaker_state"].labels(
                    service=service_name,
                    circuit_name=circuit_name,
                ).set(numeric_state)

            # Increment state change counter
            if "circuit_breaker_state_changes" in self.metrics:
                self.metrics["circuit_breaker_state_changes"].labels(
                    service=service_name,
                    circuit_name=circuit_name,
                    from_state=self.state_mapper.to_string(from_state),
                    to_state=self.state_mapper.to_string(to_state),
                ).inc()

            logger.info(
                f"Circuit breaker '{circuit_name}' state change recorded: "
                f"{from_state.value} -> {to_state.value}"
            )

        except Exception as e:
            logger.error(f"Failed to record circuit breaker state change: {e}")

    def set_state(
        self,
        circuit_name: str,
        state: CircuitBreakerState,
        service_name: str,
    ) -> None:
        """Set the current circuit breaker state."""
        try:
            if "circuit_breaker_state" in self.metrics:
                numeric_state = self.state_mapper.to_numeric(state)
                self.metrics["circuit_breaker_state"].labels(
                    service=service_name,
                    circuit_name=circuit_name,
                ).set(numeric_state)

        except Exception as e:
            logger.error(f"Failed to set circuit breaker state: {e}")

    def increment_calls(
        self,
        circuit_name: str,
        result: str,
        service_name: str,
    ) -> None:
        """Increment circuit breaker call counter."""
        try:
            if "circuit_breaker_calls_total" in self.metrics:
                self.metrics["circuit_breaker_calls_total"].labels(
                    service=service_name,
                    circuit_name=circuit_name,
                    result=result,
                ).inc()

        except Exception as e:
            logger.error(f"Failed to increment circuit breaker calls: {e}")

    def record_blocked_call(
        self,
        circuit_name: str,
        service_name: str,
    ) -> None:
        """Record a blocked call due to open circuit."""
        self.increment_calls(circuit_name, "blocked", service_name)


class NoOpMetrics:
    """No-op implementation for services without circuit breaker metrics."""

    def __init__(self, service_name: str):
        self.service_name = service_name

    def record_state_change(
        self,
        circuit_name: str,
        from_state: CircuitBreakerState,
        to_state: CircuitBreakerState,
        service_name: str,
    ) -> None:
        """No-op state change recording."""
        logger.debug(
            f"No-op: Circuit breaker '{circuit_name}' state change: "
            f"{from_state.value} -> {to_state.value}"
        )

    def set_state(
        self,
        circuit_name: str,
        state: CircuitBreakerState,
        service_name: str,
    ) -> None:
        """No-op state setting."""
        logger.debug(f"No-op: Circuit breaker '{circuit_name}' state: {state.value}")

    def increment_calls(
        self,
        circuit_name: str,
        result: str,
        service_name: str,
    ) -> None:
        """No-op call increment."""
        logger.debug(f"No-op: Circuit breaker '{circuit_name}' call: {result}")

    def record_blocked_call(
        self,
        circuit_name: str,
        service_name: str,
    ) -> None:
        """No-op blocked call recording."""
        logger.debug(f"No-op: Circuit breaker '{circuit_name}' blocked call")


def create_metrics_bridge(
    metrics_dict: Dict[str, Any],
    service_name: str,
) -> CircuitBreakerMetrics:
    """
    Create metrics bridge for circuit breaker metrics.

    Args:
        metrics_dict: Dictionary containing metrics instances
        service_name: Name of the service

    Returns:
        CircuitBreakerMetrics implementation
    """
    if not metrics_dict:
        return NoOpMetrics(service_name)

    return PrometheusCircuitBreakerMetrics(metrics_dict, service_name)
