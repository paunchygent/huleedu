"""Tests for validation_reporter module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.utils.validation_reporter import ValidationReporter, ValidationResult


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_creates_with_defaults(self) -> None:
        """Should create result with default empty messages."""
        result = ValidationResult(path=Path("test.md"), status="ok")

        assert result.path == Path("test.md")
        assert result.status == "ok"
        assert result.messages == []

    def test_creates_with_messages(self) -> None:
        """Should create result with provided messages."""
        result = ValidationResult(
            path=Path("test.md"),
            status="error",
            messages=["error 1", "error 2"],
        )

        assert result.status == "error"
        assert len(result.messages) == 2


class TestValidationReporter:
    """Tests for ValidationReporter class."""

    def test_add_ok_records_success(self) -> None:
        """Should record successful validation."""
        reporter = ValidationReporter()

        reporter.add_ok(Path("test.md"))

        assert len(reporter.results) == 1
        assert reporter.results[0].status == "ok"
        assert reporter.error_count == 0

    def test_add_error_records_error(self) -> None:
        """Should record validation error."""
        reporter = ValidationReporter()

        with patch("builtins.print"):
            reporter.add_error(Path("test.md"), "invalid format")

        assert len(reporter.results) == 1
        assert reporter.results[0].status == "error"
        assert reporter.error_count == 1

    def test_add_warning_records_warning(self) -> None:
        """Should record validation warning."""
        reporter = ValidationReporter()

        with patch("builtins.print"):
            reporter.add_warning(Path("test.md"), "missing field")

        assert len(reporter.results) == 1
        assert reporter.results[0].status == "warning"
        assert reporter.warning_count == 1

    def test_error_count_property(self) -> None:
        """Should correctly count errors."""
        reporter = ValidationReporter()

        with patch("builtins.print"):
            reporter.add_ok(Path("file1.md"))
            reporter.add_error(Path("file2.md"), "error 1")
            reporter.add_error(Path("file3.md"), "error 2")
            reporter.add_warning(Path("file4.md"), "warning")

        assert reporter.error_count == 2

    def test_warning_count_property(self) -> None:
        """Should correctly count warnings."""
        reporter = ValidationReporter()

        with patch("builtins.print"):
            reporter.add_ok(Path("file1.md"))
            reporter.add_warning(Path("file2.md"), "warning 1")
            reporter.add_warning(Path("file3.md"), "warning 2")
            reporter.add_error(Path("file4.md"), "error")

        assert reporter.warning_count == 2

    def test_exit_with_summary_returns_0_on_success(self) -> None:
        """Should return 0 when no errors."""
        reporter = ValidationReporter()
        reporter.add_ok(Path("file.md"))

        with patch("builtins.print"):
            exit_code = reporter.exit_with_summary()

        assert exit_code == 0

    def test_exit_with_summary_returns_1_on_errors(self) -> None:
        """Should return 1 when there are errors."""
        reporter = ValidationReporter()

        with patch("builtins.print"):
            reporter.add_error(Path("file.md"), "some error")
            exit_code = reporter.exit_with_summary()

        assert exit_code == 1

    def test_exit_with_summary_strict_mode_fails_on_warnings(self) -> None:
        """Should return 1 in strict mode when there are warnings."""
        reporter = ValidationReporter()

        with patch("builtins.print"):
            reporter.add_warning(Path("file.md"), "some warning")
            exit_code = reporter.exit_with_summary(strict=True)

        assert exit_code == 1

    def test_exit_with_summary_non_strict_passes_with_warnings(self) -> None:
        """Should return 0 in non-strict mode when there are only warnings."""
        reporter = ValidationReporter()

        with patch("builtins.print"):
            reporter.add_warning(Path("file.md"), "some warning")
            exit_code = reporter.exit_with_summary(strict=False)

        assert exit_code == 0

    def test_verbose_mode_prints_ok_results(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print OK results in verbose mode."""
        reporter = ValidationReporter(verbose=True)

        reporter.add_ok(Path("test.md"))

        captured = capsys.readouterr()
        assert "[OK]" in captured.out
        assert "test.md" in captured.out

    def test_non_verbose_mode_skips_ok_results(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should not print OK results in non-verbose mode."""
        reporter = ValidationReporter(verbose=False)

        reporter.add_ok(Path("test.md"))

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_prints_error_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print errors with correct format."""
        reporter = ValidationReporter()

        reporter.add_error(Path("bad-file.md"), "invalid syntax")

        captured = capsys.readouterr()
        assert "[ERROR]" in captured.out
        assert "bad-file.md" in captured.out
        assert "invalid syntax" in captured.out

    def test_prints_warning_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print warnings with correct format."""
        reporter = ValidationReporter()

        reporter.add_warning(Path("file.md"), "missing optional field")

        captured = capsys.readouterr()
        assert "[WARNING]" in captured.out
        assert "file.md" in captured.out
        assert "missing optional field" in captured.out
