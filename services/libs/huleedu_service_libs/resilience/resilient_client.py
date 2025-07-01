"""
Generic resilient client wrapper for adding circuit breaker to any protocol.

This module provides a transparent wrapper that can add circuit breaker
protection to any protocol implementation without modifying the original code.
"""

import asyncio
import functools
from typing import Any, TypeVar, cast

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker

logger = create_service_logger("resilient_client")

T = TypeVar("T")


class ResilientClientWrapper:
    """
    Generic wrapper to add circuit breaker to any protocol implementation.

    This wrapper intercepts all method calls and wraps them with circuit breaker
    protection. It's designed to be transparent - the wrapped object behaves
    exactly like the original, but with added resilience.
    """

    def __init__(self, delegate: T, circuit_breaker: CircuitBreaker) -> None:
        """
        Initialize wrapper with delegate and circuit breaker.

        Args:
            delegate: The actual implementation to wrap
            circuit_breaker: Circuit breaker to use for protection
        """
        self._delegate = delegate
        self._circuit_breaker = circuit_breaker
        # Cache wrapped methods to avoid recreating them
        self._wrapped_methods: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        """
        Intercept attribute access to wrap methods with circuit breaker.

        This is called when an attribute is not found in the wrapper itself.
        We check if it's a method on the delegate and wrap it if so.
        """
        # Get the attribute from the delegate
        attr = getattr(self._delegate, name)

        # If it's not callable, just return it as-is
        if not callable(attr):
            return attr

        # Check if we've already wrapped this method
        if name in self._wrapped_methods:
            return self._wrapped_methods[name]

        # Determine if it's an async method
        if asyncio.iscoroutinefunction(attr):
            # Create async wrapper
            @functools.wraps(attr)
            async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
                """Async method wrapper with circuit breaker."""
                logger.debug(f"Calling {name} through circuit breaker")
                return await self._circuit_breaker.call(attr, *args, **kwargs)

            self._wrapped_methods[name] = async_wrapped
            return async_wrapped
        else:
            # Create sync wrapper (though most HuleEdu methods are async)
            @functools.wraps(attr)
            def sync_wrapped(*args: Any, **kwargs: Any) -> Any:
                """Sync method wrapper with circuit breaker."""
                logger.debug(f"Calling {name} through circuit breaker")
                # For sync methods, we need to run the circuit breaker in a loop
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(
                    self._circuit_breaker.call(attr, *args, **kwargs)
                )

            self._wrapped_methods[name] = sync_wrapped
            return sync_wrapped

    def __repr__(self) -> str:
        """String representation showing wrapped type."""
        return f"ResilientClientWrapper({type(self._delegate).__name__})"


def make_resilient(
    implementation: T,
    circuit_breaker: CircuitBreaker
) -> T:
    """
    Factory function to create a resilient version of any implementation.

    This function returns an object that implements the same interface as the
    input but with circuit breaker protection on all methods.

    Args:
        implementation: The implementation to make resilient
        circuit_breaker: The circuit breaker to use

    Returns:
        A wrapped version that appears to be the same type but with protection
    """
    wrapper = ResilientClientWrapper(implementation, circuit_breaker)
    # Cast to make type checker happy - the wrapper implements the same interface
    return cast(T, wrapper)
