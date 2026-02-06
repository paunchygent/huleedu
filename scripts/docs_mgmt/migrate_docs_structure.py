#!/usr/bin/env python3
"""
Migrate docs/ to a spec-compliant structure.

Reorganizes directory structure, fixes file naming violations, and optionally
adds frontmatter to runbooks and decisions per docs/DOCS_STRUCTURE_SPEC.md.

No external dependencies required.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"

# Directory migration mappings based on audit findings
# Order matters: process archives first, then simple renames, then merges
DIRECTORY_MIGRATIONS = [
    # Archive operations first (to avoid conflicts)
    ("CONVERSATION_PROMPTS", "_archive/CONVERSATION_PROMPTS"),
    ("MIGRATION_REPORTS", "_archive/MIGRATION_REPORTS"),
    ("TEAM_COMMUNICATIONS", "_archive/TEAM_COMMUNICATIONS"),
    ("fixes", "_archive/fixes"),
    ("dependencies", "_archive/dependencies"),
    ("REFACTORING", "_archive/REFACTORING"),
    ("SERVICE_FUTURE_ENHANCEMENTS", "_archive/SERVICE_FUTURE_ENHANCEMENTS"),
    ("SERVICE_TEMPLATES", "_archive/SERVICE_TEMPLATES"),
    ("setup_environment", "_archive/setup_environment"),
    ("troubleshooting", "_archive/troubleshooting"),
    # Simple renames (case fixes)
    ("OPERATIONS", "operations"),
    ("PRD:s", "product"),
    # Dirs that map to allowed taxonomy
    ("adr", "decisions"),
    ("apis", "reference/apis"),
    ("schemas", "reference/schemas"),
    # Multiple dirs merging to same target (process first occurrence as rename)
    ("guides", "how-to"),
    ("user_guides", "how-to"),
]

# Runbook severity levels (§5)
ALLOWED_RUNBOOK_SEVERITIES = {"low", "medium", "high", "critical"}

# Decision record statuses (§6)
ALLOWED_DECISION_STATUSES = {"proposed", "accepted", "superseded", "rejected"}


def migrate_directory_structure(
    docs_root: Path, dry_run: bool = False
) -> Dict[str, List[Tuple[str, str]]]:
    """
    Migrate directory structure per DIRECTORY_MIGRATIONS.

    Args:
        docs_root: Documentation root directory
        dry_run: If True, show changes without applying

    Returns:
        Dict with keys: renamed, moved, archived, created
    """
    results: Dict[str, List[Tuple[str, str]]] = {
        "renamed": [],
        "moved": [],
        "archived": [],
        "created": [],
    }

    for old_name, new_name in DIRECTORY_MIGRATIONS:
        old_path = docs_root / old_name
        if not old_path.exists():
            continue

        new_path = docs_root / new_name

        # Check if paths are the same (case-insensitive filesystem)
        try:
            same_path = old_path.samefile(new_path)
        except FileNotFoundError:
            same_path = False

        if same_path:
            # On case-insensitive filesystems, need to rename via temp
            if old_name != new_name and not dry_run:
                temp_path = docs_root / f"_temp_{new_name}"
                old_path.rename(temp_path)
                temp_path.rename(new_path)
            results["renamed"].append((old_name, new_name))
        elif new_name.startswith("_archive/"):
            # Archive operation
            if not dry_run:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_path), str(new_path))
            results["archived"].append((old_name, new_name))
        elif "/" in new_name:
            # Nested move (e.g., apis → reference/apis)
            if not dry_run:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                # Check if target already exists
                if new_path.exists():
                    # Merge contents
                    for item in old_path.rglob("*"):
                        if item.is_file():
                            rel_path = item.relative_to(old_path)
                            target = new_path / rel_path
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(str(item), str(target))
                    shutil.rmtree(old_path)
                else:
                    # Direct move
                    shutil.move(str(old_path), str(new_path))
            results["moved"].append((old_name, new_name))
        else:
            # Simple rename
            if not dry_run:
                if new_path.exists():
                    # Target exists, merge contents
                    for item in old_path.rglob("*"):
                        if item.is_file():
                            rel_path = item.relative_to(old_path)
                            target = new_path / rel_path
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(str(item), str(target))
                    shutil.rmtree(old_path)
                else:
                    old_path.rename(new_path)
            results["renamed"].append((old_name, new_name))

    return results


def fix_filename_spaces(docs_root: Path, dry_run: bool = False) -> List[Tuple[str, str]]:
    """
    Fix filenames containing spaces by converting to kebab-case.

    Args:
        docs_root: Documentation root directory
        dry_run: If True, show changes without applying

    Returns:
        List of (old_path_rel, new_name) tuples
    """
    fixes: List[Tuple[str, str]] = []

    for p in docs_root.rglob("*.md"):
        if " " in p.name:
            # Convert to kebab-case
            new_name = p.name.replace(" ", "-").lower()
            new_path = p.parent / new_name

            if not dry_run:
                # Avoid overwrites
                if new_path.exists():
                    counter = 1
                    stem = new_path.stem
                    while new_path.exists():
                        new_name = f"{stem}-{counter}.md"
                        new_path = p.parent / new_name
                        counter += 1
                p.rename(new_path)

            rel_path = str(p.relative_to(docs_root))
            fixes.append((rel_path, new_name))

    return fixes


def infer_service_from_path(p: Path) -> str:
    """
    Infer service name from file path.

    Args:
        p: Path to file

    Returns:
        Service name or "global"
    """
    # Check if path contains service name pattern
    parts = p.parts
    for part in parts:
        if "_service" in part:
            return part
        # Check for known service names
        if part in {
            "batch_orchestrator_service",
            "class_management_service",
            "cj_assessment_service",
            "essay_lifecycle_service",
            "file_service",
            "llm_provider_service",
            "spellchecker_service",
        }:
            return part

    # Try to extract from filename
    stem = p.stem.lower()
    if "_service" in stem:
        match = re.search(r"(\w+_service)", stem)
        if match:
            return match.group(1)

    return "global"


def read_front_matter(p: Path) -> Tuple[Dict[str, str], str]:
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
    data: Dict[str, str] = {}
    for line in header.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        data[k] = v.strip("'\"")
    return data, body


def add_runbook_frontmatter(p: Path, dry_run: bool = False) -> bool:
    """
    Add runbook frontmatter if missing.

    Args:
        p: Path to runbook file
        dry_run: If True, show changes without applying

    Returns:
        True if frontmatter was added, False otherwise
    """
    content = p.read_text(encoding="utf-8")

    if content.startswith("---\n"):
        return False  # Already has frontmatter

    # Extract service name from filename or directory
    service = infer_service_from_path(p)

    frontmatter = f"""---
type: runbook
service: {service}
severity: medium
last_reviewed: {date.today().isoformat()}
---

"""

    if not dry_run:
        p.write_text(frontmatter + content, encoding="utf-8")

    return True


def add_decision_frontmatter(p: Path, dry_run: bool = False) -> bool:
    """
    Add decision frontmatter if missing.

    Args:
        p: Path to decision file
        dry_run: If True, show changes without applying

    Returns:
        True if frontmatter was added, False otherwise
    """
    content = p.read_text(encoding="utf-8")

    if content.startswith("---\n"):
        return False  # Already has frontmatter

    # Try to infer ID from filename (NNNN-descriptor.md)
    match = re.match(r"^(\d{4})-", p.stem)
    adr_id = f"ADR-{match.group(1)}" if match else "ADR-0000"

    frontmatter = f"""---
type: decision
id: {adr_id}
status: accepted
created: {date.today().isoformat()}
last_updated: {date.today().isoformat()}
---

"""

    if not dry_run:
        p.write_text(frontmatter + content, encoding="utf-8")

    return True


def add_frontmatter(docs_root: Path, dry_run: bool = False) -> Dict[str, int]:
    """
    Add frontmatter to runbooks and decisions.

    Args:
        docs_root: Documentation root directory
        dry_run: If True, show changes without applying

    Returns:
        Dict with keys: runbooks, decisions (counts)
    """
    results = {"runbooks": 0, "decisions": 0}

    # Add runbook frontmatter
    operations_dir = docs_root / "operations"
    if operations_dir.exists():
        for p in operations_dir.rglob("*.md"):
            # Skip README and INDEX files
            if p.name in {"README.md", "INDEX.md"}:
                continue
            if add_runbook_frontmatter(p, dry_run):
                results["runbooks"] += 1

    # Add decision frontmatter
    decisions_dir = docs_root / "decisions"
    if decisions_dir.exists():
        for p in decisions_dir.rglob("*.md"):
            # Skip README and INDEX files
            if p.name in {"README.md", "INDEX.md"}:
                continue
            if add_decision_frontmatter(p, dry_run):
                results["decisions"] += 1

    return results


def main(argv: list[str]) -> int:
    """
    Main CLI entry point.

    Args:
        argv: Command-line arguments

    Returns:
        Exit code (0=success, 2=usage error)
    """
    ap = argparse.ArgumentParser(description="Migrate docs/ to spec-compliant structure")
    ap.add_argument("--root", default=str(DOCS_DIR), help="Docs root directory")
    ap.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    ap.add_argument("--backup", action="store_true", help="Create backup before migration")
    ap.add_argument(
        "--add-frontmatter",
        action="store_true",
        help="Add frontmatter to runbooks/decisions",
    )
    ap.add_argument("--verbose", "-v", action="store_true", help="Detailed logging")
    ap.add_argument("--force", action="store_true", help="Skip confirmation prompts")
    args = ap.parse_args(argv)

    docs_root = Path(args.root)

    if not docs_root.exists():
        print(f"Error: {docs_root} does not exist", file=sys.stderr)
        return 2

    # Backup if requested
    if args.backup and not args.dry_run:
        backup_dir = docs_root.parent / f"documentation_backup_{date.today().isoformat()}"
        if backup_dir.exists():
            print(f"Warning: Backup directory already exists: {backup_dir}")
            if not args.force:
                response = input("Overwrite? (y/N): ")
                if response.lower() != "y":
                    print("Aborted.")
                    return 2
            shutil.rmtree(backup_dir)
        shutil.copytree(docs_root, backup_dir)
        print(f"Created backup: {backup_dir}")
        print()

    print("Documentation Migration Report")
    print("=" * 50)
    print()

    # Migrate directory structure
    print("Directory Structure Migration:")
    dir_results = migrate_directory_structure(docs_root, args.dry_run)
    for old, new in dir_results["renamed"]:
        print(f"  Renamed: {old}/ → {new}/")
    for old, new in dir_results["moved"]:
        print(f"  Moved: {old}/ → {new}/")
    for old, new in dir_results["archived"]:
        print(f"  Archived: {old}/ → {new}/")
    if not (dir_results["renamed"] or dir_results["moved"] or dir_results["archived"]):
        print("  (no directory migrations needed)")
    print()

    # Fix filename spaces
    print("File Naming Fixes:")
    filename_fixes = fix_filename_spaces(docs_root, args.dry_run)
    for old, new in filename_fixes:
        print(f"  Renamed: {old} → {new}")
    print(f"  Total: {len(filename_fixes)} file(s)")
    print()

    # Add frontmatter if requested
    if args.add_frontmatter:
        print("Frontmatter Addition:")
        fm_results = add_frontmatter(docs_root, args.dry_run)
        print(f"  Runbooks: {fm_results['runbooks']} file(s) updated")
        print(f"  Decisions: {fm_results['decisions']} file(s) updated")
        print()

    if args.dry_run:
        print("[DRY RUN] No changes applied")
    else:
        print("✓ Migration complete")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
