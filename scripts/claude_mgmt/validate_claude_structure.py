#!/usr/bin/env python3
"""
Validate .claude/ directory structure and rule file frontmatter.

Validates:
- Rule file naming conventions (NNN-descriptive-name.md or NNN.N-descriptive-name.md)
- Rule file frontmatter schema (using Pydantic RuleFrontmatter model)
- Parent-child rule relationships
- Hook documentation in hooks/README.md
- Deprecated directory usage (.claude/work/tasks/)
- Directory structure compliance
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from scripts.schemas.rule_schema import RuleFrontmatter

ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DIR = ROOT / ".claude"

# Rule file naming pattern: NNN-descriptive-name.md or NNN.N-descriptive-name.md
RULE_FILE_PATTERN = re.compile(r"^(\d{3}(?:\.\d+)?)-([a-z0-9-]+)\.md$")


def read_front_matter(p: Path) -> tuple[dict[str, Any], str]:
    """
    Parse YAML frontmatter from a file.

    Args:
        p: Path to file

    Returns:
        Tuple of (frontmatter dict, body content)
    """
    text = p.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text

    # Split on first occurrence of closing ---
    parts = text[4:].split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text

    header_text = parts[0]
    body = parts[1]

    # Parse YAML frontmatter
    try:
        data = yaml.safe_load(header_text) or {}
    except yaml.YAMLError:
        return {}, text

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


def validate_rule_frontmatter(p: Path, fm: dict[str, Any], all_rule_ids: set[str]) -> list[str]:
    """
    Validate rule file frontmatter against Pydantic schema.

    Args:
        p: Path to rule file
        fm: Parsed frontmatter dict
        all_rule_ids: Set of all valid rule IDs for cross-validation

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

    if not fm:
        errors.append("missing frontmatter")
        return errors

    # Convert date strings to date objects for Pydantic validation
    fm_copy = fm.copy()
    for date_field in ("created", "last_updated"):
        if date_field in fm_copy and isinstance(fm_copy[date_field], str):
            try:
                fm_copy[date_field] = date.fromisoformat(fm_copy[date_field])
            except ValueError:
                errors.append(
                    f"invalid date '{date_field}': '{fm_copy[date_field]}' (expected YYYY-MM-DD)"
                )
                return errors

    # Validate with Pydantic model
    try:
        rule_fm = RuleFrontmatter.model_validate(fm_copy)
    except ValidationError as e:
        for error in e.errors():
            field = ".".join(str(x) for x in error["loc"])
            msg = error["msg"]
            errors.append(f"{field}: {msg}")
        return errors

    # Additional cross-file validations
    filename_stem = p.stem

    # Validate ID matches filename
    if rule_fm.id != filename_stem:
        errors.append(f"frontmatter id '{rule_fm.id}' must match filename '{filename_stem}'")

    # Validate parent_rule reference exists
    if rule_fm.parent_rule and rule_fm.parent_rule not in all_rule_ids:
        errors.append(f"parent_rule '{rule_fm.parent_rule}' does not exist in rules directory")

    # Validate child_rules references exist
    if rule_fm.child_rules:
        for child_id in rule_fm.child_rules:
            if child_id not in all_rule_ids:
                errors.append(f"child_rule '{child_id}' does not exist in rules directory")

    return errors


def validate_rule_file(p: Path, all_rule_ids: set[str]) -> list[str]:
    """
    Validate a rule file for compliance with .claude/ specification.

    Args:
        p: Path to rule file
        all_rule_ids: Set of all valid rule IDs for cross-validation

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

    # Validate naming
    errors.extend(validate_rule_file_naming(p))

    # Parse and validate frontmatter
    fm, _ = read_front_matter(p)
    errors.extend(validate_rule_frontmatter(p, fm, all_rule_ids))

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
        # First pass: collect all rule IDs
        all_rule_ids: set[str] = set()
        rule_files: list[Path] = []

        for p in rules_dir.glob("*.md"):
            # Skip non-normative files
            if p.name in ("README.md",):
                continue

            rule_files.append(p)
            # Extract rule ID from filename
            all_rule_ids.add(p.stem)

        # Second pass: validate each rule with complete ID set
        for p in rule_files:
            rel = p.relative_to(ROOT)
            errs = validate_rule_file(p, all_rule_ids)

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
