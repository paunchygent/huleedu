#!/usr/bin/env python3
"""
Check import patterns in HuleEdu services to enforce full module paths.

This script ensures all services use full module paths for imports to prevent
conflicts in the monorepo environment.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import NamedTuple


class ImportViolation(NamedTuple):
    """Represents an import pattern violation."""

    file_path: str
    line: int
    import_statement: str
    suggestion: str


class ImportPatternChecker(ast.NodeVisitor):
    """AST visitor to check import patterns."""

    def __init__(self, file_path: Path, service_name: str):
        self.file_path = file_path
        self.service_name = service_name
        self.violations: list[ImportViolation] = []
        # Common modules that could conflict between services
        self.conflicting_modules = {
            "config",
            "protocols",
            "di",
            "api_models",
            "models_db",
            "enums_db",
            "metrics",
            "implementations",
            "startup_setup",
            "kafka_consumer",
            "event_processor",
            "worker_main",
            "api",
        }

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check 'from X import Y' statements."""
        if node.module and node.module.split(".")[0] in self.conflicting_modules:
            # This is a relative import that should be absolute
            import_str = f"from {node.module} import ..."
            suggestion = f"from services.{self.service_name}.{node.module} import ..."
            self.violations.append(
                ImportViolation(
                    file_path=str(self.file_path),
                    line=node.lineno,
                    import_statement=import_str,
                    suggestion=suggestion,
                )
            )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Check 'import X' statements."""
        for alias in node.names:
            if alias.name in self.conflicting_modules:
                import_str = f"import {alias.name}"
                suggestion = f"from services.{self.service_name} import {alias.name}"
                self.violations.append(
                    ImportViolation(
                        file_path=str(self.file_path),
                        line=node.lineno,
                        import_statement=import_str,
                        suggestion=suggestion,
                    )
                )
        self.generic_visit(node)


def check_file(file_path: Path, service_name: str) -> list[ImportViolation]:
    """Check a single Python file for import pattern violations."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        checker = ImportPatternChecker(file_path, service_name)
        checker.visit(tree)
        return checker.violations
    except Exception as e:
        print(f"Error parsing {file_path}: {e}", file=sys.stderr)
        return []


def get_service_name(file_path: Path) -> str | None:
    """Extract service name from file path."""
    parts = file_path.parts
    if "services" in parts:
        service_idx = parts.index("services")
        if service_idx + 1 < len(parts):
            return parts[service_idx + 1]
    return None


def main() -> int:
    """Main entry point."""
    root_dir = Path(__file__).parent.parent
    services_dir = root_dir / "services"

    # Services to check (excluding libs which is not a service)
    services_to_check = [
        d
        for d in services_dir.iterdir()
        if d.is_dir() and d.name != "libs" and not d.name.startswith(".")
    ]

    all_violations: list[ImportViolation] = []

    for service_dir in services_to_check:
        service_name = service_dir.name

        # Skip if no Python files
        python_files = list(service_dir.rglob("*.py"))
        if not python_files:
            continue

        print(f"\nChecking {service_name}...")

        for py_file in python_files:
            # Skip test files and __pycache__
            if "__pycache__" in str(py_file) or "/.venv/" in str(py_file):
                continue

            violations = check_file(py_file, service_name)
            all_violations.extend(violations)

    # Report results
    if all_violations:
        print(f"\n❌ Found {len(all_violations)} import pattern violations:\n")

        # Group by service
        by_service: dict[str, list[ImportViolation]] = {}
        for v in all_violations:
            service = get_service_name(Path(v.file_path))
            if service:
                by_service.setdefault(service, []).append(v)

        for service, violations in sorted(by_service.items()):
            print(f"\n{service}:")
            for v in violations:
                rel_path = Path(v.file_path).relative_to(root_dir)
                print(f"  {rel_path}:{v.line}")
                print(f"    Found:     {v.import_statement}")
                print(f"    Expected:  {v.suggestion}")

        print("\n💡 To fix these violations, update the imports to use full module paths.")
        print("   This prevents import conflicts in the monorepo environment.")
        return 1
    else:
        print("\n✅ All services use correct import patterns!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
