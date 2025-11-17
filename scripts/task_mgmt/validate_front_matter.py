#!/usr/bin/env python3
"""
Validate YAML-like front matter in TASKS markdown files. No external deps required.
- Ensures required fields exist and enum values are valid.
- Exits non-zero on failures.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "TASKS"

ALLOWED_DOMAINS = {
    "assessment",
    "content",
    "identity",
    "frontend",
    "infrastructure",
    "security",
    "integrations",
    "architecture",
    "programs",
}
ALLOWED_STATUSES = {"research", "blocked", "in_progress", "completed", "paused", "archived"}
ALLOWED_PRIORITIES = {"low", "medium", "high", "critical"}

# Top-level directories allowed under TASKS/
ALLOWED_TOP_LEVEL_DIRS = {
    "programs",
    "assessment",
    "content",
    "identity",
    "frontend",
    "infrastructure",
    "security",
    "integrations",
    "architecture",
    "archive",
}

# Files excluded from validation
EXCLUDED_FILES = {
    "_REORGANIZATION_PROPOSAL.md",
    "INDEX.md",
    "README.md",
    "HUB.md",
}

# ID validation pattern: A-Z, 0-9, _, - only; must start with uppercase letter or digit
ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]*$")

# Subdirectory naming pattern: lower_snake_case
SUBDIR_PATTERN = re.compile(r"^[a-z0-9_]+$")

FRONT_MATTER_REQUIRED = [
    "id",
    "title",
    "status",
    "priority",
    "domain",
    "owner_team",
    "created",
    "last_updated",
]


def read_front_matter(p: Path) -> Tuple[Dict[str, Any], str]:
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


def validate_no_spaces(p: Path, tasks_root: Path) -> list[str]:
    """
    Validate that no path components contain spaces.

    Args:
        p: Path to validate
        tasks_root: Root TASKS directory

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []
    rel_path = p.relative_to(tasks_root)
    for part in rel_path.parts:
        if " " in part:
            errors.append(f"path contains spaces: '{rel_path}'")
            break
    return errors


def validate_filename_id_match(p: Path, fm: Dict[str, Any]) -> list[str]:
    """
    Validate that filename (without .md) matches frontmatter id.

    Args:
        p: Path to file
        fm: Parsed frontmatter dict

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []
    filename_stem = p.stem  # filename without extension
    fm_id = fm.get("id", "")
    if filename_stem != fm_id:
        errors.append(f"filename '{p.name}' does not match id '{fm_id}'")
    return errors


def validate_id_format(fm: Dict[str, Any]) -> list[str]:
    """
    Validate that id matches pattern: A-Z, 0-9, _, - only; starts with uppercase or digit.

    Args:
        fm: Parsed frontmatter dict

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []
    fm_id = fm.get("id", "")
    if not fm_id:
        return errors  # Missing id is handled by required field validation

    if not ID_PATTERN.match(fm_id):
        # Determine specific issue for better error message
        if not fm_id[0].isupper() and not fm_id[0].isdigit():
            errors.append(f"id '{fm_id}' must start with uppercase letter or digit")
        else:
            errors.append(
                f"id '{fm_id}' contains invalid characters (must be A-Z, 0-9, _, - only)"
            )
    return errors


def validate_path_structure(p: Path, tasks_root: Path) -> list[str]:
    """
    Validate that file is in correct directory taxonomy.

    Args:
        p: Path to file
        tasks_root: Root TASKS directory

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []
    rel_path = p.relative_to(tasks_root)
    parts = rel_path.parts

    if len(parts) == 1:
        # File at root level (not in any subdirectory)
        errors.append(
            "file at root level, should be in domain directory "
            "(e.g., assessment/, frontend/, programs/)"
        )
    elif len(parts) >= 2:
        # Check top-level directory
        top_level = parts[0]
        if top_level not in ALLOWED_TOP_LEVEL_DIRS:
            allowed_str = ", ".join(sorted(ALLOWED_TOP_LEVEL_DIRS))
            errors.append(
                f"invalid top-level directory '{top_level}/' (allowed: {allowed_str})"
            )
    return errors


def validate_directory_naming(p: Path, tasks_root: Path) -> list[str]:
    """
    Validate that subdirectories use lower_snake_case.

    Args:
        p: Path to file
        tasks_root: Root TASKS directory

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []
    rel_path = p.relative_to(tasks_root)
    parts = rel_path.parts

    # Check all directory components (excluding top-level and filename)
    if len(parts) > 2:
        for subdir in parts[1:-1]:  # Skip top-level dir and filename
            if not SUBDIR_PATTERN.match(subdir):
                errors.append(f"subdirectory '{subdir}' must use lower_snake_case")
    return errors


def validate_file(p: Path, tasks_root: Path, strict: bool = False) -> list[str]:
    """
    Validate a task file for compliance with TASKS specification.

    Args:
        p: Path to file
        tasks_root: Root TASKS directory
        strict: Enable strict validation (currently unused)

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

    # Parse frontmatter
    fm, _ = read_front_matter(p)
    if not fm:
        errors.append("missing front matter")
        return errors

    # Validate required fields
    for key in FRONT_MATTER_REQUIRED:
        if key not in fm or not str(fm[key]).strip():
            errors.append(f"missing required '{key}'")

    # Validate enum fields
    if fm.get("domain") not in ALLOWED_DOMAINS:
        errors.append(f"invalid domain '{fm.get('domain')}'")
    if fm.get("status") not in ALLOWED_STATUSES:
        errors.append(f"invalid status '{fm.get('status')}'")
    if fm.get("priority") not in ALLOWED_PRIORITIES:
        errors.append(f"invalid priority '{fm.get('priority')}'")

    # Validate dates
    for key in ("created", "last_updated"):
        val = str(fm.get(key, ""))
        try:
            dt.date.fromisoformat(val)
        except ValueError:
            errors.append(f"invalid date '{key}': '{val}' (expected YYYY-MM-DD)")

    # Owner team default
    if not fm.get("owner_team"):
        errors.append("owner_team must be set (e.g., 'agents')")

    # New validations from spec §13
    errors.extend(validate_filename_id_match(p, fm))
    errors.extend(validate_id_format(fm))

    return errors


def should_exclude_file(p: Path, tasks_root: Path, exclude_archive: bool) -> bool:
    """
    Determine if a file should be excluded from validation.

    Args:
        p: Path to file
        tasks_root: Root TASKS directory
        exclude_archive: Whether to exclude archived files

    Returns:
        True if file should be excluded, False otherwise
    """
    # Exclude archive files if flag is set
    if exclude_archive and "archive" in p.parts:
        return True

    # Exclude specific files
    if p.name in EXCLUDED_FILES:
        return True

    return False


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Validate TASKS frontmatter and structure compliance"
    )
    ap.add_argument("--root", default=str(TASKS_DIR), help="Tasks root directory")
    ap.add_argument("--exclude-archive", action="store_true", default=True)
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root)
    failures = 0

    for p in root.rglob("*.md"):
        # Check exclusions first
        if should_exclude_file(p, root, args.exclude_archive):
            continue

        rel = p.relative_to(ROOT)
        errs: list[str] = []

        # Validate path structure (before parsing frontmatter)
        errs.extend(validate_no_spaces(p, root))
        errs.extend(validate_path_structure(p, root))
        errs.extend(validate_directory_naming(p, root))

        # Validate file content and frontmatter
        errs.extend(validate_file(p, root))

        if errs:
            failures += 1
            print(f"[ERROR] {rel}:")
            for e in errs:
                print(f"  - {e}")
        elif args.verbose:
            print(f"[OK] {rel}")

    if failures:
        print(f"\nValidation failed: {failures} file(s) with errors.")
        return 1
    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
