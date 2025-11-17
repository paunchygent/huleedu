#!/usr/bin/env python3
"""
Validate documentation structure per docs/DOCS_STRUCTURE_SPEC.md.
No external deps required.

Validates:
- Top-level directory taxonomy (§3)
- File naming conventions (§4)
- Directory naming conventions (§4)
- Runbook frontmatter in operations/ (§5, warnings)
- Decision record frontmatter in decisions/ (§6, warnings)
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"

# Top-level directories allowed under documentation/ (§3)
ALLOWED_TOP_LEVEL_DIRS = {
    "overview",
    "architecture",
    "services",
    "operations",
    "how-to",
    "reference",
    "decisions",
    "product",
    "research",
}

# Runbook severity levels (§5)
ALLOWED_RUNBOOK_SEVERITIES = {"low", "medium", "high", "critical"}

# Decision record statuses (§6)
ALLOWED_DECISION_STATUSES = {"proposed", "accepted", "superseded", "rejected"}

# File naming patterns (§4)
# kebab-case: lowercase letters, digits, hyphens only
KEBAB_CASE_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# SCREAMING_SNAKE_CASE: uppercase letters, digits, underscores only
SCREAMING_SNAKE_CASE_PATTERN = re.compile(r"^[A-Z0-9]+(_[A-Z0-9]+)*$")

# Directory naming patterns (§4)
# kebab-case for directories
DIR_KEBAB_CASE_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# lower_snake_case for directories
DIR_SNAKE_CASE_PATTERN = re.compile(r"^[a-z0-9_]+$")

# Decision record filename pattern (§6)
DECISION_FILENAME_PATTERN = re.compile(r"^\d{4}-[a-z0-9-]+$")

# Files excluded from validation
EXCLUDED_FILES = {
    "README.md",
    "INDEX.md",
}


def read_front_matter(p: Path) -> Tuple[Dict[str, Any], str]:
    """
    Parse YAML-like frontmatter from a Markdown file.

    Args:
        p: Path to file

    Returns:
        Tuple of (frontmatter dict, body text)
    """
    text = p.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text
    header = parts[0][4:]
    body = parts[1]
    data: Dict[str, Any] = {}
    for line in header.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if v.startswith("[") and v.endswith("]"):
            # crude list parsing of comma-separated quoted items
            items = [i.strip().strip("'\"") for i in v[1:-1].split(",") if i.strip()]
            data[k] = items
        else:
            data[k] = v.strip("'\"")
    return data, body


def validate_top_level_taxonomy(docs_root: Path) -> list[str]:
    """
    Check that only allowed top-level directories exist (§3).

    Args:
        docs_root: Documentation root directory

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []
    if not docs_root.exists():
        return errors

    for item in docs_root.iterdir():
        if not item.is_dir():
            continue
        if item.name.startswith("."):
            continue
        # Exclude _archive directory (temporary migration artifact)
        if item.name == "_archive":
            continue
        if item.name not in ALLOWED_TOP_LEVEL_DIRS:
            allowed_str = ", ".join(sorted(ALLOWED_TOP_LEVEL_DIRS))
            errors.append(f"invalid top-level directory '{item.name}/' (allowed: {allowed_str})")
    return errors


def validate_filename_format(p: Path) -> list[str]:
    """
    Check filename is kebab-case or SCREAMING_SNAKE_CASE, no spaces (§4).

    Args:
        p: Path to file

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []
    filename = p.name
    stem = p.stem

    # Check for .md extension
    if not filename.endswith(".md"):
        errors.append(f"filename '{filename}' must use .md extension")
        return errors

    # Check for spaces
    if " " in stem:
        errors.append(
            f"filename '{filename}' must be kebab-case or SCREAMING_SNAKE_CASE (no spaces)"
        )
        return errors

    # Check against patterns
    if not KEBAB_CASE_PATTERN.match(stem) and not SCREAMING_SNAKE_CASE_PATTERN.match(stem):
        errors.append(f"filename '{filename}' must be kebab-case or SCREAMING_SNAKE_CASE")
    return errors


def validate_directory_naming(p: Path, docs_root: Path) -> list[str]:
    """
    Check directory names are kebab-case or lower_snake_case (§4).

    Args:
        p: Path to file
        docs_root: Documentation root directory

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []
    rel_path = p.relative_to(docs_root)
    parts = rel_path.parts

    # Check all directory components (excluding filename)
    for dirname in parts[:-1]:
        if not DIR_KEBAB_CASE_PATTERN.match(dirname) and not DIR_SNAKE_CASE_PATTERN.match(dirname):
            errors.append(f"directory '{dirname}' must be kebab-case or lower_snake_case")
    return errors


def validate_no_spaces(p: Path, docs_root: Path) -> list[str]:
    """
    Check no spaces in path (§4).

    Args:
        p: Path to file
        docs_root: Documentation root directory

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []
    rel_path = p.relative_to(docs_root)
    for part in rel_path.parts:
        if " " in part:
            errors.append(f"path contains spaces: '{rel_path}'")
            break
    return errors


def validate_runbook_frontmatter(p: Path, docs_root: Path) -> list[str]:
    """
    Validate runbook frontmatter in operations/ (§5, warnings).

    Args:
        p: Path to file
        docs_root: Documentation root directory

    Returns:
        List of warning messages (empty if valid)
    """
    warnings: list[str] = []
    rel_path = p.relative_to(docs_root)

    # Only validate files in operations/
    if "operations" not in rel_path.parts:
        return warnings

    fm, _ = read_front_matter(p)

    # Check if frontmatter exists
    if not fm:
        warnings.append("[WARNING] runbook missing frontmatter")
        return warnings

    # Check for type field
    if fm.get("type") != "runbook":
        warnings.append("[WARNING] runbook frontmatter should have type: runbook")

    # Check required fields
    required_fields = ["service", "severity", "last_reviewed"]
    for field in required_fields:
        if field not in fm or not str(fm[field]).strip():
            warnings.append(f"[WARNING] runbook missing frontmatter field '{field}'")

    # Validate severity enum
    severity = fm.get("severity")
    if severity and severity not in ALLOWED_RUNBOOK_SEVERITIES:
        valid_str = "|".join(sorted(ALLOWED_RUNBOOK_SEVERITIES))
        warnings.append(f"[WARNING] runbook severity '{severity}' invalid (expected: {valid_str})")

    # Validate last_reviewed date
    last_reviewed = fm.get("last_reviewed")
    if last_reviewed:
        try:
            dt.date.fromisoformat(str(last_reviewed))
        except ValueError:
            warnings.append(
                f"[WARNING] runbook last_reviewed '{last_reviewed}' invalid (expected: YYYY-MM-DD)"
            )

    return warnings


def validate_decision_frontmatter(p: Path, docs_root: Path) -> list[str]:
    """
    Validate decision frontmatter in decisions/ (§6, warnings).

    Args:
        p: Path to file
        docs_root: Documentation root directory

    Returns:
        List of warning messages (empty if valid)
    """
    warnings: list[str] = []
    rel_path = p.relative_to(docs_root)

    # Only validate files in decisions/
    if "decisions" not in rel_path.parts:
        return warnings

    # Check filename pattern (NNNN-short-descriptor.md)
    stem = p.stem
    if not DECISION_FILENAME_PATTERN.match(stem):
        warnings.append(
            "[WARNING] decision record should follow pattern 'NNNN-short-descriptor.md'"
        )

    fm, _ = read_front_matter(p)

    # Check if frontmatter exists
    if not fm:
        warnings.append("[WARNING] decision record missing frontmatter")
        return warnings

    # Check for type field
    if fm.get("type") != "decision":
        warnings.append("[WARNING] decision record frontmatter should have type: decision")

    # Check required fields
    required_fields = ["id", "status", "created", "last_updated"]
    for field in required_fields:
        if field not in fm or not str(fm[field]).strip():
            warnings.append(f"[WARNING] decision record missing frontmatter field '{field}'")

    # Validate status enum
    status = fm.get("status")
    if status and status not in ALLOWED_DECISION_STATUSES:
        valid_str = "|".join(sorted(ALLOWED_DECISION_STATUSES))
        warnings.append(f"[WARNING] decision status '{status}' invalid (expected: {valid_str})")

    # Validate dates
    for field in ["created", "last_updated"]:
        date_val = fm.get(field)
        if date_val:
            try:
                dt.date.fromisoformat(str(date_val))
            except ValueError:
                warnings.append(
                    f"[WARNING] decision record {field} '{date_val}' invalid (expected: YYYY-MM-DD)"
                )

    return warnings


def validate_file(p: Path, docs_root: Path) -> Tuple[list[str], list[str]]:
    """
    Validate a documentation file for compliance with DOCS_STRUCTURE_SPEC.

    Args:
        p: Path to file
        docs_root: Documentation root directory

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Validate no spaces in path
    errors.extend(validate_no_spaces(p, docs_root))

    # Validate filename format
    errors.extend(validate_filename_format(p))

    # Validate directory naming
    errors.extend(validate_directory_naming(p, docs_root))

    # Validate runbook frontmatter (warnings)
    warnings.extend(validate_runbook_frontmatter(p, docs_root))

    # Validate decision frontmatter (warnings)
    warnings.extend(validate_decision_frontmatter(p, docs_root))

    return errors, warnings


def should_exclude_file(p: Path) -> bool:
    """
    Determine if a file should be excluded from validation.

    Args:
        p: Path to file

    Returns:
        True if file should be excluded, False otherwise
    """
    # Exclude spec files
    if p.name in EXCLUDED_FILES:
        return True

    # Exclude files in _archive/ directory
    if "_archive" in p.parts:
        return True

    return False


def main(argv: list[str]) -> int:
    """
    Main CLI entry point.

    Args:
        argv: Command-line arguments

    Returns:
        Exit code (0=success, 1=validation errors, 2=usage error)
    """
    ap = argparse.ArgumentParser(
        description="Validate documentation structure per DOCS_STRUCTURE_SPEC.md"
    )
    ap.add_argument("--root", default=str(DOCS_DIR), help="Documentation root directory")
    ap.add_argument("--verbose", "-v", action="store_true", help="Show all files validated")
    ap.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.exists():
        print(f"Error: Documentation root does not exist: {root}", file=sys.stderr)
        return 2

    # Validate top-level taxonomy first
    taxonomy_errors = validate_top_level_taxonomy(root)
    if taxonomy_errors:
        print("[ERROR] Top-level directory structure:")
        for e in taxonomy_errors:
            print(f"  - {e}")
        print()

    # Validate individual files
    error_count = 0
    warning_count = 0

    for p in root.rglob("*.md"):
        # Check exclusions
        if should_exclude_file(p):
            continue

        rel = p.relative_to(root)
        errors, warnings = validate_file(p, root)

        if errors:
            error_count += 1
            print(f"[ERROR] {rel}:")
            for e in errors:
                print(f"  - {e}")

        if warnings:
            warning_count += 1
            print(f"[WARNING] {rel}:")
            for w in warnings:
                print(f"  - {w}")

        if not errors and not warnings and args.verbose:
            print(f"[OK] {rel}")

    # Print summary
    print()
    if taxonomy_errors:
        error_count += 1

    if error_count or (args.strict and warning_count):
        if args.strict and warning_count:
            print(
                f"Validation failed: {error_count} file(s) with errors, "
                f"{warning_count} file(s) with warnings (strict mode)."
            )
        else:
            print(f"Validation failed: {error_count} file(s) with errors.")
        return 1

    if warning_count:
        print(
            f"Validation passed with warnings: {warning_count} file(s) with warnings "
            "(use --strict to treat as errors)."
        )
    else:
        print("Validation passed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
