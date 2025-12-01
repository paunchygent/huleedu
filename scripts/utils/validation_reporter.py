"""Unified validation reporting for task/docs/rules validators."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidationResult:
    """Result for a single file validation."""

    path: Path
    status: str  # "ok", "error", "warning"
    messages: list[str] = field(default_factory=list)


class ValidationReporter:
    """Collects and reports validation results with consistent formatting."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: list[ValidationResult] = []

    def add_ok(self, path: Path) -> None:
        """Record successful validation."""
        self.results.append(ValidationResult(path, "ok"))
        if self.verbose:
            self._print_result(path, "OK", "")

    def add_error(self, path: Path, message: str) -> None:
        """Record validation error."""
        result = ValidationResult(path, "error", [message])
        self.results.append(result)
        self._print_result(path, "ERROR", message)

    def add_warning(self, path: Path, message: str) -> None:
        """Record validation warning."""
        result = ValidationResult(path, "warning", [message])
        self.results.append(result)
        self._print_result(path, "WARNING", message)

    def _print_result(self, path: Path, status: str, message: str) -> None:
        """Print formatted result line."""
        try:
            rel_path = path.relative_to(Path.cwd())
        except ValueError:
            rel_path = path

        prefix = f"[{status}]"
        line = f"{prefix} {rel_path}"
        if message:
            line += f": {message}"
        print(line)

    @property
    def error_count(self) -> int:
        """Count of validation errors."""
        return sum(1 for r in self.results if r.status == "error")

    @property
    def warning_count(self) -> int:
        """Count of validation warnings."""
        return sum(1 for r in self.results if r.status == "warning")

    def exit_with_summary(self, strict: bool = False) -> int:
        """Print summary and return exit code.

        Args:
            strict: If True, treat warnings as errors

        Returns:
            Exit code (0=success, 1=failure)
        """
        errors = self.error_count
        warnings = self.warning_count

        if errors > 0:
            print(f"\nValidation failed: {errors} error(s)")
            return 1

        if warnings > 0:
            if strict:
                print(f"\nValidation failed (strict mode): {warnings} warning(s)")
                return 1
            print(f"\nValidation passed with {warnings} warning(s)")
        else:
            print("\nValidation passed.")

        return 0
