"""Tests for Result[T, E] monad implementation."""

from dataclasses import dataclass

import pytest
from huleedu_service_libs import Result


@dataclass
class CustomError:
    """Custom error type for testing."""

    code: str
    message: str


class TestResultOk:
    """Tests for Result.ok() success path."""

    def test_ok_creates_success_result_with_string(self) -> None:
        """Test Result.ok() with string value."""
        result: Result[str, str] = Result.ok("success")

        assert result.is_ok
        assert not result.is_err
        assert result.value == "success"

    def test_ok_creates_success_result_with_int(self) -> None:
        """Test Result.ok() with integer value."""
        result: Result[int, str] = Result.ok(42)

        assert result.is_ok
        assert not result.is_err
        assert result.value == 42

    def test_ok_creates_success_result_with_custom_dataclass(self) -> None:
        """Test Result.ok() with custom dataclass."""

        @dataclass
        class Data:
            id: str
            count: int

        data = Data(id="abc", count=10)
        result: Result[Data, str] = Result.ok(data)

        assert result.is_ok
        assert not result.is_err
        assert result.value == data
        assert result.value.id == "abc"
        assert result.value.count == 10

    def test_ok_accessing_error_raises_value_error(self) -> None:
        """Test accessing error on Result.ok raises ValueError."""
        result: Result[str, str] = Result.ok("success")

        with pytest.raises(ValueError, match="Called error on Result.ok"):
            _ = result.error


class TestResultErr:
    """Tests for Result.err() error path."""

    def test_err_creates_error_result_with_string(self) -> None:
        """Test Result.err() with string error."""
        result: Result[str, str] = Result.err("something went wrong")

        assert result.is_err
        assert not result.is_ok
        assert result.error == "something went wrong"

    def test_err_creates_error_result_with_custom_dataclass(self) -> None:
        """Test Result.err() with custom error dataclass."""
        error = CustomError(code="NOT_FOUND", message="Resource not found")
        result: Result[str, CustomError] = Result.err(error)

        assert result.is_err
        assert not result.is_ok
        assert result.error == error
        assert result.error.code == "NOT_FOUND"
        assert result.error.message == "Resource not found"

    def test_err_accessing_value_raises_value_error(self) -> None:
        """Test accessing value on Result.err raises ValueError."""
        result: Result[str, str] = Result.err("error")

        with pytest.raises(ValueError, match="Called value on Result.err"):
            _ = result.value


class TestResultProperties:
    """Tests for Result properties and type safety."""

    def test_is_ok_and_is_err_are_mutually_exclusive(self) -> None:
        """Test is_ok and is_err are never both True."""
        ok_result: Result[str, str] = Result.ok("value")
        assert ok_result.is_ok
        assert not ok_result.is_err

        err_result: Result[str, str] = Result.err("error")
        assert err_result.is_err
        assert not err_result.is_ok

    def test_result_is_frozen_dataclass(self) -> None:
        """Test Result instances are immutable (frozen=True)."""
        result: Result[str, str] = Result.ok("value")

        with pytest.raises(AttributeError):
            result._value = "changed"  # type: ignore

        with pytest.raises(AttributeError):
            result._error = "changed"  # type: ignore


class TestResultUsagePatterns:
    """Tests for common Result usage patterns."""

    def test_conditional_branching_on_success(self) -> None:
        """Test typical success handling pattern."""
        result: Result[int, str] = Result.ok(100)

        if result.is_ok:
            processed = result.value * 2
            assert processed == 200
        else:
            pytest.fail("Should not reach error branch")

    def test_conditional_branching_on_error(self) -> None:
        """Test typical error handling pattern."""
        result: Result[int, str] = Result.err("computation_failed")

        if result.is_err:
            error_message = result.error
            assert error_message == "computation_failed"
        else:
            pytest.fail("Should not reach success branch")

    def test_function_returning_result_success(self) -> None:
        """Test function returning Result in success case."""

        def divide(a: int, b: int) -> Result[float, str]:
            if b == 0:
                return Result.err("division_by_zero")
            return Result.ok(a / b)

        result = divide(10, 2)
        assert result.is_ok
        assert result.value == 5.0

    def test_function_returning_result_error(self) -> None:
        """Test function returning Result in error case."""

        def divide(a: int, b: int) -> Result[float, str]:
            if b == 0:
                return Result.err("division_by_zero")
            return Result.ok(a / b)

        result = divide(10, 0)
        assert result.is_err
        assert result.error == "division_by_zero"

    def test_empty_string_as_valid_success_value(self) -> None:
        """Test that empty string is a valid success value."""
        result: Result[str, str] = Result.ok("")

        assert result.is_ok
        assert result.value == ""

    def test_none_handling_requires_optional_type(self) -> None:
        """Test that None can be wrapped in Result with proper typing."""
        result: Result[str | None, str] = Result.ok(None)

        assert result.is_ok
        assert result.value is None
