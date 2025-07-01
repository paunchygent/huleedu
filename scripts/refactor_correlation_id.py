#!/usr/bin/env python3
"""
Script to refactor correlation_id from optional to required across the HuleEdu codebase.

This script will:
1. Update method signatures to make correlation_id required (UUID instead of UUID | None)
2. Update calls to ensure correlation_id is always provided
3. Generate UUIDs where correlation_id is currently None
4. Update type annotations
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

# Patterns to match and replace
PATTERNS = [
    # Method signatures with correlation_id as optional parameter
    (r"correlation_id:\s*UUID\s*\|\s*None\s*=\s*None", "correlation_id: UUID"),
    # Type annotations in method signatures
    (r"correlation_id:\s*Optional\[UUID\]\s*=\s*None", "correlation_id: UUID"),
    # String type annotations (for protocols that use str)
    (r"correlation_id:\s*str\s*\|\s*None\s*=\s*None", "correlation_id: UUID"),
    # Import statements that might need UUID
    (r"from typing import (.*?)$", lambda m: add_uuid_import(m.group(0))),
    # EventEnvelope correlation_id field definition
    (
        r"correlation_id:\s*UUID\s*\|\s*None\s*=\s*None",
        "correlation_id: UUID = Field(default_factory=uuid4)",
    ),
]

# Patterns for method calls that need updating
CALL_PATTERNS = [
    # Cases where correlation_id is explicitly None
    (r"correlation_id\s*=\s*None", "correlation_id=uuid4()"),
    # Cases where correlation_id is conditionally None
    (
        r"correlation_id\s*=\s*(.+?)\s+if\s+.+?\s+else\s+None",
        lambda m: f"correlation_id={m.group(1)} if {m.group(1)} else uuid4()",
    ),
    # String conversion cases
    (r"str\(correlation_id\)\s+if\s+correlation_id\s+else\s+None", "correlation_id"),
]

# Files/directories to exclude
EXCLUDE_PATTERNS = [
    "*.pyc",
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
    "*.egg-info",
    "test_*.py",  # We'll handle test files separately
]

# Service directories to process
SERVICE_DIRS = [
    "services/batch_orchestrator_service",
    "services/essay_lifecycle_service",
    "services/spell_checker_service",
    "services/cj_assessment_service",
    "services/api_gateway_service",
    "services/file_service",
    "services/result_aggregator_service",
    "services/content_service",
    "common_core/src/common_core",
]


def add_uuid_import(import_line: str) -> str:
    """Add UUID to import statement if not already present."""
    if "UUID" not in import_line:
        # Check if this is a multiline import
        if import_line.strip().endswith("("):
            return import_line
        # Add UUID to the import
        return import_line.rstrip() + "\nfrom uuid import UUID, uuid4"
    return import_line


def should_process_file(file_path: Path) -> bool:
    """Check if file should be processed."""
    # Skip if matches exclude pattern
    for pattern in EXCLUDE_PATTERNS:
        if file_path.match(pattern):
            return False

    # Only process Python files
    if not file_path.suffix == ".py":
        return False

    return True


def find_files_to_process(base_dir: Path) -> List[Path]:
    """Find all Python files that need processing."""
    files = []

    for service_dir in SERVICE_DIRS:
        service_path = base_dir / service_dir
        if service_path.exists():
            for file_path in service_path.rglob("*.py"):
                if should_process_file(file_path):
                    files.append(file_path)

    return files


def update_file_content(content: str, file_path: Path) -> Tuple[str, List[str]]:
    """Update file content with new patterns."""
    changes = []
    updated_content = content

    # Apply signature patterns
    for pattern, replacement in PATTERNS:
        if callable(replacement):
            # Handle lambda replacements
            matches = list(re.finditer(pattern, updated_content, re.MULTILINE))
            for match in reversed(matches):  # Process in reverse to maintain positions
                new_text = replacement(match)
                updated_content = (
                    updated_content[: match.start()] + new_text + updated_content[match.end() :]
                )
                if new_text != match.group(0):
                    changes.append(f"Replaced '{match.group(0)}' with '{new_text}'")
        else:
            # Simple string replacement
            new_content, count = re.subn(pattern, replacement, updated_content, flags=re.MULTILINE)
            if count > 0:
                updated_content = new_content
                changes.append(f"Replaced {count} occurrences of pattern '{pattern}'")

    # Apply call patterns
    for pattern, replacement in CALL_PATTERNS:
        if callable(replacement):
            matches = list(re.finditer(pattern, updated_content, re.MULTILINE))
            for match in reversed(matches):
                new_text = replacement(match)
                updated_content = (
                    updated_content[: match.start()] + new_text + updated_content[match.end() :]
                )
                if new_text != match.group(0):
                    changes.append(f"Updated call: '{match.group(0)}' to '{new_text}'")
        else:
            new_content, count = re.subn(pattern, replacement, updated_content, flags=re.MULTILINE)
            if count > 0:
                updated_content = new_content
                changes.append(f"Updated {count} method calls with pattern '{pattern}'")

    # Ensure UUID imports are present if needed
    if "correlation_id" in updated_content and "UUID" in updated_content:
        if "from uuid import" not in updated_content:
            # Add import at the top after __future__ imports
            lines = updated_content.split("\n")
            import_added = False
            for i, line in enumerate(lines):
                if (
                    line.strip()
                    and not line.startswith("from __future__")
                    and not line.startswith("#")
                    and not line.startswith('"""')
                ):
                    lines.insert(i, "from uuid import UUID, uuid4")
                    import_added = True
                    break
            if import_added:
                updated_content = "\n".join(lines)
                changes.append("Added UUID import")

    return updated_content, changes


def process_files(files: List[Path], dry_run: bool = True) -> None:
    """Process all files and apply changes."""
    total_changes = 0
    files_modified = 0

    for file_path in files:
        try:
            content = file_path.read_text()
            updated_content, changes = update_file_content(content, file_path)

            if changes:
                print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing {file_path}:")
                for change in changes:
                    print(f"  - {change}")

                if not dry_run:
                    file_path.write_text(updated_content)

                files_modified += 1
                total_changes += len(changes)

        except Exception as e:
            print(f"Error processing {file_path}: {e}", file=sys.stderr)

    print(
        f"\n{'[DRY RUN] Would modify' if dry_run else 'Modified'} {files_modified} files with {total_changes} changes total"
    )


def find_remaining_optional_correlation_ids(base_dir: Path) -> None:
    """Find any remaining optional correlation_ids after refactoring."""
    print("\nSearching for remaining optional correlation_ids...")

    patterns = [
        r"correlation_id:\s*\w+\s*\|\s*None",
        r"correlation_id:\s*Optional\[",
        r"correlation_id\s*=\s*None",
    ]

    found_any = False
    for service_dir in SERVICE_DIRS:
        service_path = base_dir / service_dir
        if service_path.exists():
            for file_path in service_path.rglob("*.py"):
                if should_process_file(file_path):
                    content = file_path.read_text()
                    for pattern in patterns:
                        matches = re.findall(pattern, content)
                        if matches:
                            if not found_any:
                                print("\nRemaining optional correlation_ids found:")
                                found_any = True
                            print(f"\n{file_path}:")
                            for match in matches:
                                print(f"  - {match}")

    if not found_any:
        print("No remaining optional correlation_ids found!")


def main():
    parser = argparse.ArgumentParser(
        description="Refactor correlation_id from optional to required"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would be changed without modifying files (default: True)",
    )
    parser.add_argument("--apply", action="store_true", help="Actually apply the changes to files")
    parser.add_argument(
        "--check", action="store_true", help="Check for remaining optional correlation_ids"
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.cwd(),
        help="Base directory of the project (default: current directory)",
    )

    args = parser.parse_args()

    if args.check:
        find_remaining_optional_correlation_ids(args.base_dir)
        return

    print(f"Scanning for files in {args.base_dir}")
    files = find_files_to_process(args.base_dir)
    print(f"Found {len(files)} Python files to process")

    if files:
        process_files(files, dry_run=not args.apply)

        if not args.apply:
            print("\nTo apply these changes, run with --apply flag")
    else:
        print("No files found to process")


if __name__ == "__main__":
    main()
