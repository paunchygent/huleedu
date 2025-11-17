#!/usr/bin/env python3
"""
Migrate TASKS to lowercase kebab-case for consistency with documentation standards.

Changes:
- Converts all task IDs to lowercase kebab-case
- Renames files to match lowercase IDs
- Updates frontmatter accordingly
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "TASKS"

EXCLUDED_FILES = {
    "_REORGANIZATION_PROPOSAL.md",
    "INDEX.md",
    "README.md",
    "HUB.md",
}


def read_front_matter(p: Path) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from markdown file."""
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
            items = [i.strip().strip("'\"") for i in v[1:-1].split(",") if i.strip()]
            data[k] = items
        else:
            data[k] = v.strip("'\"")
    return data, body


def to_lowercase_kebab(s: str) -> str:
    """
    Convert SCREAMING-KEBAB or SCREAMING_SNAKE to lowercase-kebab.

    Examples:
        TASK-LLM-FILTERING -> task-llm-filtering
        TASK_FOO_BAR -> task-foo-bar
        PHASE3_CJ_CONFIDENCE_HUB -> phase3-cj-confidence-hub
    """
    # Replace underscores with hyphens
    s = s.replace("_", "-")
    # Convert to lowercase
    s = s.lower()
    # Normalize multiple hyphens to single
    s = re.sub(r"-+", "-", s)
    return s


def migrate_file(src: Path, tasks_root: Path, dry_run: bool = False) -> Dict[str, Any]:
    """
    Migrate a single file to lowercase kebab-case.

    Args:
        src: Source file path
        tasks_root: Root TASKS directory
        dry_run: If True, don't make changes, just report

    Returns:
        Dict with migration result
    """
    result = {
        "src": str(src.relative_to(ROOT)),
        "dest": None,
        "action": None,
        "old_id": None,
        "new_id": None,
    }

    try:
        # Read frontmatter
        fm, body = read_front_matter(src)

        if not fm or "id" not in fm:
            result["action"] = "skipped_no_id"
            return result

        old_id = fm["id"]
        new_id = to_lowercase_kebab(old_id)

        # Check if already lowercase
        if old_id == new_id:
            result["action"] = "skipped_already_lowercase"
            return result

        result["old_id"] = old_id
        result["new_id"] = new_id

        # Update frontmatter
        fm["id"] = new_id

        # Rebuild frontmatter
        fm_lines = ["---"]
        for key in [
            "id",
            "title",
            "type",
            "status",
            "priority",
            "domain",
            "service",
            "owner_team",
            "owner",
            "program",
            "created",
            "last_updated",
            "related",
            "labels",
        ]:
            if key not in fm:
                continue
            value = fm[key]
            if isinstance(value, list):
                if value:
                    items_str = ", ".join([f'"{item}"' for item in value])
                    fm_lines.append(f"{key}: [{items_str}]")
                else:
                    fm_lines.append(f"{key}: []")
            else:
                fm_lines.append(f'{key}: "{value}"' if value else f'{key}: ""')
        fm_lines.append("---")

        new_content = "\n".join(fm_lines) + "\n" + body

        # Determine new filename
        new_filename = new_id + ".md"
        dest = src.parent / new_filename

        if not dry_run:
            # Write new content
            dest.write_text(new_content, encoding="utf-8")

            # Delete old file if renamed
            if dest != src:
                src.unlink()

        result["dest"] = str(dest.relative_to(ROOT))
        result["action"] = "migrated"

    except Exception as e:
        result["action"] = "error"
        result["error"] = str(e)

    return result


def main(argv: list[str]) -> int:
    """Main CLI entry point."""
    ap = argparse.ArgumentParser(description="Migrate TASKS to lowercase kebab-case")
    ap.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    tasks_root = TASKS_DIR

    if not tasks_root.exists():
        print(f"Error: {tasks_root} does not exist")
        return 2

    print("TASKS Lowercase Migration")
    print("=" * 60)
    print()

    if args.dry_run:
        print("[DRY RUN] No changes will be made")
        print()

    # Process all task files
    migrated = []
    skipped_lowercase = []
    skipped_no_id = []
    errors = []

    for p in sorted(tasks_root.rglob("*.md")):
        # Skip excluded files
        if p.name in EXCLUDED_FILES:
            continue

        # Skip archive
        if "archive" in p.parts:
            continue

        result = migrate_file(p, tasks_root, dry_run=args.dry_run)

        if result["action"] == "migrated":
            migrated.append(result)
            if args.verbose or args.dry_run:
                print(f"✓ {result['src']}")
                print(f"  {result['old_id']} → {result['new_id']}")
                if result["dest"] != result["src"]:
                    print(f"  Renamed: {Path(result['dest']).name}")
        elif result["action"] == "skipped_already_lowercase":
            skipped_lowercase.append(result)
            if args.verbose:
                print(f"○ {result['src']} (already lowercase)")
        elif result["action"] == "skipped_no_id":
            skipped_no_id.append(result)
            if args.verbose:
                print(f"○ {result['src']} (no ID field)")
        elif result["action"] == "error":
            errors.append(result)
            print(f"✗ {result['src']}: {result.get('error', 'unknown error')}")

    # Summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print()
    print(f"Migrated to lowercase: {len(migrated)}")
    print(f"Already lowercase: {len(skipped_lowercase)}")
    print(f"No ID field: {len(skipped_no_id)}")
    print(f"Errors: {len(errors)}")

    if args.dry_run:
        print()
        print("[DRY RUN] No changes were made.")
        print("Run without --dry-run to apply changes.")

    return 0 if len(errors) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
