"""Result monad for discriminated union of success/failure states.

This module provides a lightweight Result type for operations that may fail,
avoiding exception-based control flow in non-boundary code.

Example:
    ```python
    from huleedu_service_libs import Result

    def fetch_data(storage_id: str) -> Result[str, str]:
        if not storage_id:
            return Result.err("empty_storage_id")

        content = _fetch_from_storage(storage_id)
        if content is None:
            return Result.err("not_found")

        return Result.ok(content)

    # Usage
    result = fetch_data("abc123")
    if result.is_ok:
        data = result.value
        process(data)
    else:
        logger.error(f"Fetch failed: {result.error}")
    ```
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True)
class Result(Generic[T, E]):
    """Result monad for discriminated union of success/failure states.

    Provides a lightweight Result type for operations that may fail,
    avoiding exception-based control flow in non-boundary code.
    """

    _value: T | None = None
    _error: E | None = None

    @classmethod
    def ok(cls, value: T) -> Result[T, E]:
        """Create a successful Result wrapping a value."""
        return cls(_value=value, _error=None)

    @classmethod
    def err(cls, error: E) -> Result[T, E]:
        """Create a failed Result wrapping an error."""
        return cls(_value=None, _error=error)

    @property
    def is_ok(self) -> bool:
        """Check if this Result represents success."""
        return self._error is None

    @property
    def is_err(self) -> bool:
        """Check if this Result represents failure."""
        return self._error is not None

    @property
    def value(self) -> T:
        """Get the success value. Raises ValueError if called on Result.err."""
        if self._error is not None:
            raise ValueError("Called value on Result.err")
        return self._value  # type: ignore

    @property
    def error(self) -> E:
        """Get the error. Raises ValueError if called on Result.ok."""
        if self._error is None:
            raise ValueError("Called error on Result.ok")
        return self._error
