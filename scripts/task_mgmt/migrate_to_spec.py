#!/usr/bin/env python3
"""
Migrate TASKS/ to spec-compliant structure.

- Generates frontmatter for all files missing it
- Moves files to correct domain directories
- Renames directories to spec-compliant names
- Fixes naming violations
- Idempotent: safe to run multiple times

Usage:
    python -m scripts.task_mgmt.migrate_to_spec --dry-run  # Preview changes
    python -m scripts.task_mgmt.migrate_to_spec --backup   # Create backup first
    python -m scripts.task_mgmt.migrate_to_spec            # Execute migration
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

from pydantic import ValidationError

from scripts.schemas.task_schema import (
    TaskFrontmatter,
    TaskStatus,
)

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

# Files excluded from migration
EXCLUDED_FILES = {
    "_REORGANIZATION_PROPOSAL.md",
    "INDEX.md",
    "README.md",
}


def read_front_matter(p: Path) -> Tuple[Dict[str, Any], str]:
    """
    Parse frontmatter from a markdown file.

    Args:
        p: Path to markdown file

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


def infer_domain(filepath: Path, content: str) -> str:
    """
    Infer domain from filename and content using heuristics.

    Args:
        filepath: Path to file
        content: File content

    Returns:
        Domain name (one of ALLOWED_DOMAINS)
    """
    filename_lower = filepath.stem.lower()
    content.lower()

    # Programs (multi-domain initiatives)
    if "cj_confidence" in str(filepath) or "phase3" in filename_lower:
        return "programs"

    # Integrations (LLM providers, external APIs, SIS) - check BEFORE assessment
    # This is important because some LLM tasks mention assessment but are primarily integration work
    integration_keywords = [
        "integration",
        "llm-provider",
        "llm_provider",
        "llm-model",
        "llm-parameter",
        "openai",
        "anthropic",
        "api-client",
        "sis",
        "oneroster",
        "clever",
        "classlink",
    ]
    if any(kw in filename_lower for kw in integration_keywords):
        return "integrations"

    # Assessment (CJ, NLP, grading, rubrics)
    assessment_keywords = [
        "cj",
        "assessment",
        "grading",
        "nlp",
        "language-tool",
        "languagetool",
        "rubric",
        "bayesian",
        "consensus",
        "scoring",
        "essay",
        "spellcheck",
        "eng5",
        "batch",
    ]
    if any(kw in filename_lower for kw in assessment_keywords):
        return "assessment"

    # Frontend (Svelte, SPA, CORS, websocket)
    frontend_keywords = ["svelte", "frontend", "spa", "cors", "websocket", "upload"]
    if any(kw in filename_lower for kw in frontend_keywords):
        return "frontend"

    # Identity (auth, JWT, roles)
    identity_keywords = [
        "identity",
        "auth",
        "jwt",
        "rs256",
        "role",
        "permission",
        "sso",
        "rbac",
    ]
    if any(kw in filename_lower for kw in identity_keywords):
        return "identity"

    # Infrastructure (Docker, CI/CD, environment, observability)
    infra_keywords = [
        "docker",
        "ci-cd",
        "environment",
        "observability",
        "deployment",
        "compose",
        "container",
        "slo",
        "alert",
        "runbook",
    ]
    if any(kw in filename_lower for kw in infra_keywords):
        return "infrastructure"

    # Architecture (multi-tenancy, BFF, API design, cross-cutting)
    arch_keywords = [
        "architecture",
        "multi-tenant",
        "bff",
        "api-productization",
        "contract",
        "event-driven",
        "roadmap",
    ]
    if any(kw in filename_lower for kw in arch_keywords):
        return "architecture"

    # Content (content service, prompt storage)
    content_keywords = ["content-service", "prompt", "storage-reference"]
    if any(kw in filename_lower for kw in content_keywords):
        return "content"

    # Security (AppSec, secrets, audit)
    security_keywords = [
        "security",
        "secret",
        "audit",
        "vulnerability",
        "compliance",
        "gdpr",
        "ferpa",
    ]
    if any(kw in filename_lower for kw in security_keywords):
        return "security"

    # Default: assessment (most tasks are assessment-related)
    return "assessment"


def extract_title(content: str, filename: str) -> str:
    """
    Extract title from first heading or generate from filename.

    Args:
        content: File content
        filename: Filename stem

    Returns:
        Title string
    """
    # Look for first # heading
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()

    # Fallback: humanize filename
    # Convert TASK-XXX-SOME-NAME → Task XXX Some Name
    humanized = filename.replace("-", " ").replace("_", " ")
    return humanized.title()


def normalize_id(filename_stem: str) -> str:
    """
    Normalize filename stem to valid ID format.

    - Converts to uppercase
    - Replaces spaces with underscores
    - Removes invalid characters
    - Ensures starts with uppercase letter or digit

    Args:
        filename_stem: Filename without extension

    Returns:
        Normalized ID string
    """
    # Replace spaces with underscores
    normalized = filename_stem.replace(" ", "_")

    # Convert to uppercase
    normalized = normalized.upper()

    # Remove invalid characters (keep only A-Z, 0-9, _, -)
    normalized = re.sub(r"[^A-Z0-9_-]", "", normalized)

    # Ensure starts with uppercase letter or digit
    if normalized and not (normalized[0].isupper() or normalized[0].isdigit()):
        normalized = "TASK_" + normalized

    return normalized


def generate_frontmatter(
    filepath: Path, content: str, program: str = "", created_date: str = ""
) -> str:
    """
    Generate frontmatter for a task file.

    Args:
        filepath: Path to file
        content: File content
        program: Optional program key
        created_date: Optional creation date (defaults to today)

    Returns:
        Formatted YAML frontmatter string
    """
    filename_stem = filepath.stem
    task_id = normalize_id(filename_stem)
    title = extract_title(content, filename_stem)
    domain = infer_domain(filepath, content)

    # Use file creation time if available, otherwise today
    if not created_date:
        try:
            stat = filepath.stat()
            created_dt = dt.datetime.fromtimestamp(stat.st_birthtime)
            created_date = created_dt.date().isoformat()
        except (AttributeError, OSError):
            created_date = dt.date.today().isoformat()

    today = dt.date.today().isoformat()

    fm = {
        "id": task_id,
        "title": title,
        "type": "task",
        "status": TaskStatus.proposed.value,
        "priority": "medium",
        "domain": domain,
        "service": "",
        "owner_team": "agents",
        "owner": "",
        "program": program,
        "created": created_date,
        "last_updated": today,
        "related": [],
        "labels": [],
    }

    # Special case: HUB files (HUB.md or *_HUB.md)
    if filepath.name == "HUB.md" or filepath.stem.endswith("_HUB"):
        fm["type"] = "programme"
        if not program:
            # Extract program from filename if not provided
            # e.g., PHASE3_CJ_CONFIDENCE_HUB → cj_confidence
            stem = filepath.stem.replace("_HUB", "")
            if "CJ_CONFIDENCE" in stem:
                program = "cj_confidence"
                fm["program"] = program
        if program and filepath.name == "HUB.md":
            fm["id"] = f"{program.upper()}_HUB"

    # Validate before emitting text to catch enum/domain issues early
    try:
        TaskFrontmatter.model_validate(fm)
    except ValidationError as e:
        errors = "; ".join(
            f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()
        )
        raise ValueError(f"Frontmatter validation failed for {filepath}: {errors}") from e

    lines = ["---"]
    for key, value in fm.items():
        if isinstance(value, list):
            if value:
                items_str = ", ".join(f"'{item}'" for item in value)
                lines.append(f"{key}: [{items_str}]")
            else:
                lines.append(f"{key}: []")
        else:
            lines.append(f"{key}: '{value}'")
    lines.append("---")

    return "\n".join(lines)


def determine_target_path(src: Path, fm: Dict[str, Any], tasks_root: Path) -> Path:
    """
    Determine target path for a file based on its frontmatter.

    Args:
        src: Source file path
        fm: Frontmatter dict
        tasks_root: Root TASKS directory

    Returns:
        Target path for the file
    """
    domain = fm.get("domain", "assessment")
    program = fm.get("program", "")
    filename = src.name

    # Normalize filename to match ID
    task_id = fm.get("id", "")
    if task_id and not filename.startswith(task_id):
        filename = f"{task_id}.md"

    # Get relative path to determine subdirectory structure
    rel_path = src.relative_to(tasks_root)

    # Special handling for programs
    if program:
        # Programs go under programs/<program_name>/
        return tasks_root / "programs" / program / filename
    elif domain == "programs":
        # If domain is programs but no program specified, leave as-is
        return tasks_root / "programs" / filename
    else:
        # Regular domain placement
        # Check if file is in a special subdirectory that should be preserved
        if len(rel_path.parts) > 1:
            current_top_level = rel_path.parts[0]

            # If file is in nlp_lang_tool/, preserve that subdirectory under new domain
            if current_top_level == "nlp_lang_tool":
                return tasks_root / domain / "nlp_lang_tool" / filename

            # If file is in phase3_cj_confidence/, it should go to programs
            # (this case should be handled by program logic above)
            if current_top_level == "phase3_cj_confidence":
                return tasks_root / "programs" / "cj_confidence" / filename

            # If file is already in a domain directory, just change domain if needed
            if current_top_level in {
                "assessment",
                "content",
                "identity",
                "frontend",
                "infrastructure",
                "security",
                "integrations",
                "architecture",
            }:
                # File is already in a domain, just update domain if different
                if len(rel_path.parts) > 2:
                    # Has subdirectory: domain/subdir/file.md
                    subdir_path = Path(*rel_path.parts[1:-1])
                    return tasks_root / domain / subdir_path / filename
                else:
                    # No subdirectory: domain/file.md
                    return tasks_root / domain / filename

        # File is at root level - put it in domain directory
        return tasks_root / domain / filename


def migrate_file(src: Path, tasks_root: Path, dry_run: bool = False) -> Dict[str, Any]:
    """
    Migrate a single file: add frontmatter and move to correct location.

    Args:
        src: Source file path
        tasks_root: Root TASKS directory
        dry_run: If True, don't make changes, just report

    Returns:
        Dict with migration result information
    """
    result = {
        "src": str(src.relative_to(ROOT)),
        "dest": None,
        "action": None,
        "error": None,
    }

    try:
        # Read existing content
        fm, body = read_front_matter(src)

        # Check if already migrated (has frontmatter)
        if fm:
            result["action"] = "skipped_has_frontmatter"
            return result

        # Read full content for domain inference
        content = src.read_text(encoding="utf-8")

        # Determine program from current location
        program = ""
        rel_path = src.relative_to(tasks_root)
        if "phase3_cj_confidence" in rel_path.parts:
            program = "cj_confidence"
        elif "programs" in rel_path.parts and len(rel_path.parts) > 1:
            program = rel_path.parts[1]

        # Generate frontmatter
        fm_text = generate_frontmatter(src, content, program)

        # Parse generated frontmatter to get domain
        temp_path = Path("/tmp/temp_migrate.md")
        temp_path.write_text(fm_text + "\n" + body, encoding="utf-8")
        fm_generated, _ = read_front_matter(temp_path)

        # Determine target path
        dest = determine_target_path(src, fm_generated, tasks_root)

        # Build new content
        new_content = fm_text + "\n" + body

        if not dry_run:
            # Create target directory
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Write file to new location
            dest.write_text(new_content, encoding="utf-8")

            # Delete old file if different location
            if dest != src:
                src.unlink()

        result["dest"] = str(dest.relative_to(ROOT))
        result["action"] = "migrated"
        if dest != src:
            result["moved"] = True

    except Exception as e:
        result["error"] = str(e)
        result["action"] = "error"

    return result


def migrate_directory_structure(tasks_root: Path, dry_run: bool = False) -> Dict[str, Any]:
    """
    Migrate directory structure to spec compliance.

    - Rename archived/ → archive/
    - Move nlp_lang_tool/ → assessment/nlp_lang_tool/
    - Move phase3_cj_confidence/ → programs/cj_confidence/
    - Delete notes/

    Args:
        tasks_root: Root TASKS directory
        dry_run: If True, don't make changes, just report

    Returns:
        Dict with structure migration results
    """
    results = {
        "renamed": [],
        "moved": [],
        "deleted": [],
        "errors": [],
    }

    # 1. Rename archived/ → archive/
    archived_dir = tasks_root / "archived"
    archive_dir = tasks_root / "archive"
    if archived_dir.exists() and not archive_dir.exists():
        if not dry_run:
            archived_dir.rename(archive_dir)
        results["renamed"].append(("archived/", "archive/"))

    # 2. Move nlp_lang_tool/ → assessment/nlp_lang_tool/
    nlp_src = tasks_root / "nlp_lang_tool"
    nlp_dest = tasks_root / "assessment" / "nlp_lang_tool"
    if nlp_src.exists():
        if nlp_dest.exists():
            # Already migrated, skip
            pass
        else:
            if not dry_run:
                nlp_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(nlp_src), str(nlp_dest))
            results["moved"].append(("nlp_lang_tool/", "assessment/nlp_lang_tool/"))

    # 3. Move phase3_cj_confidence/ → programs/cj_confidence/
    phase3_src = tasks_root / "phase3_cj_confidence"
    phase3_dest = tasks_root / "programs" / "cj_confidence"
    if phase3_src.exists():
        if phase3_dest.exists():
            # Already migrated, skip
            pass
        else:
            if not dry_run:
                phase3_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(phase3_src), str(phase3_dest))
            results["moved"].append(("phase3_cj_confidence/", "programs/cj_confidence/"))

    # 4. Delete notes/ directory
    notes_dir = tasks_root / "notes"
    if notes_dir.exists():
        try:
            # List files before deletion for reporting
            notes_files = list(notes_dir.rglob("*"))
            file_count = len([f for f in notes_files if f.is_file()])

            if not dry_run:
                shutil.rmtree(notes_dir)

            results["deleted"].append(f"notes/ ({file_count} files)")
        except Exception as e:
            results["errors"].append(f"Failed to delete notes/: {e}")

    return results


def fix_filename_spaces(tasks_root: Path, dry_run: bool = False) -> list[Tuple[str, str]]:
    """
    Fix filenames containing spaces.

    Args:
        tasks_root: Root TASKS directory
        dry_run: If True, don't make changes, just report

    Returns:
        List of (old_name, new_name) tuples
    """
    renames = []

    for p in tasks_root.rglob("*.md"):
        if " " in p.name:
            # Normalize: replace spaces with hyphens, uppercase
            new_name = normalize_id(p.stem) + ".md"
            new_path = p.parent / new_name

            renames.append((str(p.relative_to(ROOT)), str(new_path.relative_to(ROOT))))

            if not dry_run:
                p.rename(new_path)

    return renames


def main(argv: list[str]) -> int:
    """Main CLI entry point."""
    ap = argparse.ArgumentParser(description="Migrate TASKS/ to spec-compliant structure")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    ap.add_argument(
        "--backup",
        action="store_true",
        help="Create backup of TASKS/ before migration",
    )
    ap.add_argument("--verbose", "-v", action="store_true", help="Detailed logging")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts",
    )
    args = ap.parse_args(argv)

    tasks_root = TASKS_DIR

    if not tasks_root.exists():
        print(f"Error: TASKS directory not found at {tasks_root}", file=sys.stderr)
        return 1

    # Confirmation prompt
    if not args.dry_run and not args.force:
        print("This will migrate TASKS/ directory structure and add frontmatter.")
        print("Use --dry-run to preview changes first.")
        response = input("Continue? [y/N] ")
        if response.lower() not in ("y", "yes"):
            print("Aborted.")
            return 0

    # Create backup if requested
    if args.backup and not args.dry_run:
        backup_path = ROOT / f"TASKS_backup_{dt.datetime.now():%Y%m%d_%H%M%S}"
        print(f"Creating backup at {backup_path}")
        shutil.copytree(tasks_root, backup_path)

    print("\nTASKS Migration Report")
    print("=" * 60)

    # Phase 1: Fix filename spaces FIRST (before directory migration)
    print("\n1. Fixing Filename Spaces...")
    print("-" * 60)
    space_renames = fix_filename_spaces(tasks_root, dry_run=args.dry_run)
    if space_renames:
        for old, new in space_renames:
            print(f"  Renamed: {old}")
            print(f"        → {new}")
    else:
        print("  No files with spaces found.")

    # Phase 2: Migrate directory structure
    print("\n2. Directory Structure Migration...")
    print("-" * 60)
    struct_results = migrate_directory_structure(tasks_root, dry_run=args.dry_run)

    if struct_results["renamed"]:
        print("  Renamed:")
        for old, new in struct_results["renamed"]:
            print(f"    {old} → {new}")

    if struct_results["moved"]:
        print("  Moved:")
        for old, new in struct_results["moved"]:
            print(f"    {old} → {new}")

    if struct_results["deleted"]:
        print("  Deleted:")
        for item in struct_results["deleted"]:
            print(f"    {item}")

    if struct_results["errors"]:
        print("  Errors:")
        for error in struct_results["errors"]:
            print(f"    {error}")

    if not any(
        [
            struct_results["renamed"],
            struct_results["moved"],
            struct_results["deleted"],
        ]
    ):
        print("  No directory changes needed.")

    # Phase 3: Migrate individual files
    print("\n3. File Migrations...")
    print("-" * 60)

    migrated_count = 0
    skipped_count = 0
    error_count = 0
    domain_counts: Dict[str, int] = {}

    for p in sorted(tasks_root.rglob("*.md")):
        # Skip excluded files
        if p.name in EXCLUDED_FILES:
            continue

        # Skip archive files
        if "archive" in p.parts:
            continue

        # Skip files that no longer exist (already moved by directory migration)
        if not p.exists():
            continue

        result = migrate_file(p, tasks_root, dry_run=args.dry_run)

        if result["action"] == "migrated":
            migrated_count += 1
            # Track domain counts - read from destination path
            dest_path = ROOT / result["dest"]
            if dest_path.exists():
                fm, _ = read_front_matter(dest_path)
                domain = fm.get("domain", "unknown")
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

            if args.verbose:
                print(f"  ✓ {result['src']}")
                if result.get("moved"):
                    print(f"    → {result['dest']}")
        elif result["action"] == "skipped_has_frontmatter":
            skipped_count += 1
            if args.verbose:
                print(f"  ○ {result['src']} (already has frontmatter)")
        elif result["action"] == "error":
            error_count += 1
            print(f"  ✗ {result['src']}: {result['error']}")

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    if space_renames:
        print(f"\nFilename fixes: {len(space_renames)}")

    if any(
        [
            struct_results["renamed"],
            struct_results["moved"],
            struct_results["deleted"],
        ]
    ):
        print("\nDirectory changes:")
        print(f"  Renamed: {len(struct_results['renamed'])}")
        print(f"  Moved: {len(struct_results['moved'])}")
        print(f"  Deleted: {len(struct_results['deleted'])}")

    print("\nFile migrations:")
    print(f"  Generated frontmatter: {migrated_count}")
    print(f"  Already migrated: {skipped_count}")
    print(f"  Errors: {error_count}")

    if domain_counts:
        print("\nFiles by domain:")
        for domain in sorted(domain_counts.keys()):
            print(f"  {domain}: {domain_counts[domain]}")

    if args.dry_run:
        print("\n[DRY RUN] No changes were made.")
        print("Run without --dry-run to apply changes.")

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
