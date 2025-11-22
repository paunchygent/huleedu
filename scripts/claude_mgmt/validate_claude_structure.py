#!/usr/bin/env python3
"""
Validate .claude/ directory structure and rule file frontmatter.
No external dependencies required.

Validates:
- Rule file naming conventions (NNN-descriptive-name.md or NNN.N-descriptive-name.md)
- Rule file frontmatter schema
- Hook documentation in hooks/README.md
- Deprecated directory usage (.claude/work/tasks/)
- Directory structure compliance
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DIR = ROOT / ".claude"

# Rule file naming pattern: NNN-descriptive-name.md or NNN.N-descriptive-name.md
RULE_FILE_PATTERN = re.compile(r"^(\d{3}(?:\.\d+)?)-([a-z0-9-]+)\.md$")

# Allowed rule categories
ALLOWED_CATEGORIES = {
    "foundation",
    "architecture",
    "implementation",
    "testing",
    "documentation",
    "operations",
}

# Allowed priority levels
ALLOWED_PRIORITIES = {"critical", "high", "medium", "low"}

# Allowed applies_to values
ALLOWED_APPLIES_TO = {
    "all",
    "backend",
    "frontend",
    "infrastructure",
}

# Required frontmatter fields for rule files
RULE_FRONTMATTER_REQUIRED = [
    "id",
    "title",
    "category",
    "priority",
    "applies_to",
    "created",
    "last_updated",
]


def read_front_matter(p: Path) -> Tuple[Dict[str, Any], str]:
    """
    Parse YAML-like frontmatter from a file.

    Args:
        p: Path to file

    Returns:
        Tuple of (frontmatter dict, body content)
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
            # Parse list of comma-separated quoted items
            items = [i.strip().strip("'\"") for i in v[1:-1].split(",") if i.strip()]
            data[k] = items
        else:
            data[k] = v.strip("'\"")
    return data, body


def validate_rule_file_naming(p: Path) -> list[str]:
    """
    Validate that rule file follows NNN-descriptive-name.md pattern.

    Args:
        p: Path to rule file

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []
    filename = p.name

    if not RULE_FILE_PATTERN.match(filename):
        errors.append(
            f"filename '{filename}' must follow pattern 'NNN-descriptive-name.md' "
            "or 'NNN.N-descriptive-name.md' "
            "(e.g., '010-foundational-principles.md' or '020.1-content-service-architecture.md')"
        )

    return errors


def validate_rule_frontmatter(p: Path, fm: Dict[str, Any]) -> list[str]:
    """
    Validate rule file frontmatter against schema.

    Args:
        p: Path to rule file
        fm: Parsed frontmatter dict

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

    if not fm:
        errors.append("missing frontmatter")
        return errors

    # Validate required fields
    for key in RULE_FRONTMATTER_REQUIRED:
        if key not in fm or not str(fm.get(key, "")).strip():
            errors.append(f"missing required field '{key}'")

    # Validate id matches filename
    filename_stem = p.stem
    fm_id = fm.get("id", "")
    if fm_id != filename_stem:
        errors.append(f"frontmatter id '{fm_id}' must match filename '{filename_stem}'")

    # Validate category
    category = fm.get("category", "")
    if category and category not in ALLOWED_CATEGORIES:
        allowed_str = ", ".join(sorted(ALLOWED_CATEGORIES))
        errors.append(f"invalid category '{category}' (allowed: {allowed_str})")

    # Validate priority
    priority = fm.get("priority", "")
    if priority and priority not in ALLOWED_PRIORITIES:
        allowed_str = ", ".join(sorted(ALLOWED_PRIORITIES))
        errors.append(f"invalid priority '{priority}' (allowed: {allowed_str})")

    # Validate applies_to (can be single value or service name)
    applies_to = fm.get("applies_to", "")
    if applies_to and applies_to not in ALLOWED_APPLIES_TO:
        # Allow specific service names (e.g., "cj_assessment_service")
        if not re.match(r"^[a-z][a-z0-9_]*$", applies_to):
            allowed_str = ", ".join(sorted(ALLOWED_APPLIES_TO))
            errors.append(
                f"invalid applies_to '{applies_to}' "
                f"(allowed: {allowed_str} or specific service name)"
            )

    # Validate dates
    for key in ("created", "last_updated"):
        val = str(fm.get(key, ""))
        if val:
            try:
                dt.date.fromisoformat(val)
            except ValueError:
                errors.append(f"invalid date '{key}': '{val}' (expected YYYY-MM-DD)")

    return errors


def validate_rule_file(p: Path) -> list[str]:
    """
    Validate a rule file for compliance with .claude/ specification.

    Args:
        p: Path to rule file

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

    # Validate naming
    errors.extend(validate_rule_file_naming(p))

    # Parse and validate frontmatter
    fm, _ = read_front_matter(p)
    errors.extend(validate_rule_frontmatter(p, fm))

    return errors


def check_hooks_documentation(claude_dir: Path) -> list[str]:
    """
    Check that all hook files are documented in hooks/README.md.

    Args:
        claude_dir: Path to .claude directory

    Returns:
        List of warning messages
    """
    warnings: list[str] = []
    hooks_dir = claude_dir / "hooks"

    if not hooks_dir.exists():
        return warnings

    # Find all .sh hook files
    hook_files = list(hooks_dir.glob("*.sh"))

    if not hook_files:
        return warnings

    # Check if hooks/README.md exists
    readme_path = hooks_dir / "README.md"
    if not readme_path.exists():
        warnings.append("hooks/README.md does not exist - hooks should be documented")
        return warnings

    # Read README content
    readme_content = readme_path.read_text(encoding="utf-8")

    # Check each hook is mentioned in README
    for hook_file in hook_files:
        if hook_file.name not in readme_content:
            warnings.append(f"hook '{hook_file.name}' not documented in hooks/README.md")

    return warnings


def check_deprecated_directories(claude_dir: Path) -> list[str]:
    """
    Check for usage of deprecated .claude/work/tasks/ directory.

    Args:
        claude_dir: Path to .claude directory

    Returns:
        List of warning messages
    """
    warnings: list[str] = []
    deprecated_tasks = claude_dir / "work" / "tasks"

    if not deprecated_tasks.exists():
        return warnings

    # Count markdown files in deprecated directory
    md_files = list(deprecated_tasks.glob("*.md"))

    if md_files:
        warnings.append(
            f".claude/work/tasks/ contains {len(md_files)} files - "
            "this directory is deprecated, migrate to TASKS/"
        )

    return warnings


def validate_directory_structure(claude_dir: Path) -> list[str]:
    """
    Validate .claude/ directory structure compliance.

    Args:
        claude_dir: Path to .claude directory

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

    # Required directories
    required_dirs = ["rules", "hooks", "work"]

    for dir_name in required_dirs:
        dir_path = claude_dir / dir_name
        if not dir_path.exists():
            errors.append(f"required directory '.claude/{dir_name}/' does not exist")

    return errors


def main(argv: list[str]) -> int:
    """Main entry point."""
    ap = argparse.ArgumentParser(
        description="Validate .claude/ directory structure and rule frontmatter"
    )
    ap.add_argument("--root", default=str(CLAUDE_DIR), help=".claude directory path")
    ap.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    ap.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = ap.parse_args(argv)

    claude_root = Path(args.root)

    if not claude_root.exists():
        print(f"[ERROR] .claude directory not found at {claude_root}")
        return 1

    failures = 0
    warnings_count = 0

    # Validate directory structure
    struct_errors = validate_directory_structure(claude_root)
    if struct_errors:
        failures += 1
        print("[ERROR] Directory structure:")
        for e in struct_errors:
            print(f"  - {e}")

    # Validate rule files
    rules_dir = claude_root / "rules"
    if rules_dir.exists():
        for p in rules_dir.glob("*.md"):
            # Skip non-normative files
            if p.name in ("README.md",):
                continue

            rel = p.relative_to(ROOT)
            errs = validate_rule_file(p)

            if errs:
                failures += 1
                print(f"[ERROR] {rel}:")
                for e in errs:
                    print(f"  - {e}")
            elif args.verbose:
                print(f"[OK] {rel}")

    # Check hooks documentation
    hook_warnings = check_hooks_documentation(claude_root)
    if hook_warnings:
        warnings_count += len(hook_warnings)
        for w in hook_warnings:
            print(f"[WARNING] {w}")

    # Check deprecated directories
    deprecated_warnings = check_deprecated_directories(claude_root)
    if deprecated_warnings:
        warnings_count += len(deprecated_warnings)
        for w in deprecated_warnings:
            print(f"[WARNING] {w}")

    # Summary
    if failures:
        print(f"\nValidation failed: {failures} file(s) with errors.")
        return 1

    if warnings_count and args.strict:
        print(f"\nValidation failed (strict mode): {warnings_count} warning(s).")
        return 1

    if warnings_count and not args.strict:
        print(f"\nValidation passed with {warnings_count} warning(s).")
        return 0

    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
