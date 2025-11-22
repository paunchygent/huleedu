#!/usr/bin/env python3
"""
Filter and query TASKS by frontmatter fields.

Usage examples:
  # Filter by priority
  python scripts/task_mgmt/filter_tasks.py --priority high --priority critical

  # Filter by status
  python scripts/task_mgmt/filter_tasks.py --status in_progress --status blocked

  # Filter by service
  python scripts/task_mgmt/filter_tasks.py --service essay_lifecycle_service

  # Filter by domain
  python scripts/task_mgmt/filter_tasks.py --domain assessment --domain frontend

  # Combine filters
  python scripts/task_mgmt/filter_tasks.py --priority high --status in_progress --domain assessment

  # Date filters (created after date)
  python scripts/task_mgmt/filter_tasks.py --created-after 2025-11-01

  # Updated in last N days
  python scripts/task_mgmt/filter_tasks.py --updated-last-days 7

  # Output formats
  python scripts/task_mgmt/filter_tasks.py --priority high --format table
  python scripts/task_mgmt/filter_tasks.py --priority high --format json
  python scripts/task_mgmt/filter_tasks.py --priority high --format paths  # just file paths

  # Exclude archived tasks (default: excluded)
  python scripts/task_mgmt/filter_tasks.py --include-archive --status completed

  # Sort results
  python scripts/task_mgmt/filter_tasks.py --sort priority --sort created
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "TASKS"

EXCLUDED_FILES = {
    "_REORGANIZATION_PROPOSAL.md",
    "INDEX.md",
    "README.md",
    "HUB.md",
}

ALLOWED_PRIORITIES = {"low", "medium", "high", "critical"}
ALLOWED_STATUSES = {"research", "blocked", "in_progress", "completed", "paused", "archived"}
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

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def read_front_matter(p: Path) -> Tuple[Dict[str, Any], str]:
    """Parse YAML-like front matter from markdown file."""
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


def should_exclude_file(p: Path, include_archive: bool) -> bool:
    """Determine if file should be excluded from filtering."""
    if not include_archive and "archive" in p.parts:
        return True
    if p.name in EXCLUDED_FILES:
        return True
    return False


def parse_date(date_str: str) -> dt.date | None:
    """Parse ISO date string, return None if invalid."""
    try:
        return dt.date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def matches_filters(
    fm: Dict[str, Any],
    priorities: set[str],
    statuses: set[str],
    domains: set[str],
    services: set[str],
    programs: set[str],
    owners: set[str],
    created_after: dt.date | None,
    created_before: dt.date | None,
    updated_after: dt.date | None,
    updated_last_days: int | None,
) -> bool:
    """Check if task matches all filter criteria."""
    # Priority filter
    if priorities and fm.get("priority") not in priorities:
        return False

    # Status filter
    if statuses and fm.get("status") not in statuses:
        return False

    # Domain filter
    if domains and fm.get("domain") not in domains:
        return False

    # Service filter (only if service is specified in task)
    if services:
        task_service = fm.get("service", "")
        if not task_service or task_service not in services:
            return False

    # Program filter
    if programs:
        task_program = fm.get("program", "")
        if not task_program or task_program not in programs:
            return False

    # Owner filter
    if owners:
        task_owner = fm.get("owner", "")
        if not task_owner or task_owner not in owners:
            return False

    # Date filters
    created_date = parse_date(fm.get("created", ""))
    if created_after and created_date and created_date < created_after:
        return False
    if created_before and created_date and created_date > created_before:
        return False

    updated_date = parse_date(fm.get("last_updated", ""))
    if updated_after and updated_date and updated_date < updated_after:
        return False

    if updated_last_days is not None and updated_date:
        cutoff = dt.date.today() - dt.timedelta(days=updated_last_days)
        if updated_date < cutoff:
            return False

    return True


def sort_tasks(
    tasks: List[Tuple[Path, Dict[str, Any]]], sort_keys: List[str]
) -> List[Tuple[Path, Dict[str, Any]]]:
    """Sort tasks by specified keys (applied in order)."""

    def sort_value(item: Tuple[Path, Dict[str, Any]], key: str) -> Any:
        _, fm = item
        if key == "priority":
            return PRIORITY_ORDER.get(fm.get("priority", "medium"), 2)
        if key == "created":
            d = parse_date(fm.get("created", ""))
            return d if d else dt.date.min
        if key == "updated" or key == "last_updated":
            d = parse_date(fm.get("last_updated", ""))
            return d if d else dt.date.min
        if key == "title":
            return fm.get("title", "").lower()
        if key == "status":
            return fm.get("status", "")
        if key == "domain":
            return fm.get("domain", "")
        if key == "service":
            return fm.get("service", "")
        return ""

    result = tasks[:]
    # Sort in reverse order of keys to apply them correctly
    for key in reversed(sort_keys):
        result = sorted(result, key=lambda x: sort_value(x, key))
    return result


def format_table(tasks: List[Tuple[Path, Dict[str, Any]]]) -> str:
    """Format tasks as a table."""
    if not tasks:
        return "No tasks found matching filters."

    # Calculate column widths
    max_title = max(len(fm.get("title", "")) for _, fm in tasks)
    max_title = min(max_title, 50)  # cap at 50 chars

    lines = []
    header = (
        f"{'Priority':<8} {'Status':<12} {'Domain':<14} {'Service':<25} "
        f"{'Title':<{max_title}} {'Updated':<10}"
    )
    lines.append(header)
    lines.append("-" * (8 + 12 + 14 + 25 + max_title + 10 + 6))

    for path, fm in tasks:
        title = fm.get("title", "")[:max_title]
        priority = fm.get("priority", "")[:8]
        status = fm.get("status", "")[:12]
        domain = fm.get("domain", "")[:14]
        service = fm.get("service", "")[:25]
        updated = fm.get("last_updated", "")[:10]

        row = (
            f"{priority:<8} {status:<12} {domain:<14} {service:<25} "
            f"{title:<{max_title}} {updated:<10}"
        )
        lines.append(row)

    return "\n".join(lines)


def format_list(tasks: List[Tuple[Path, Dict[str, Any]]]) -> str:
    """Format tasks as a list with details."""
    if not tasks:
        return "No tasks found matching filters."

    lines = []
    for path, fm in tasks:
        rel_path = path.relative_to(ROOT)
        lines.append(f"\n## {fm.get('title', 'Untitled')}")
        lines.append(f"   Path: {rel_path}")
        lines.append(f"   ID: {fm.get('id', 'N/A')}")
        lines.append(
            f"   Priority: {fm.get('priority', 'N/A')} | Status: {fm.get('status', 'N/A')}"
        )
        lines.append(f"   Domain: {fm.get('domain', 'N/A')}")
        if fm.get("service"):
            lines.append(f"   Service: {fm.get('service')}")
        if fm.get("program"):
            lines.append(f"   Program: {fm.get('program')}")
        lines.append(
            f"   Created: {fm.get('created', 'N/A')} | Updated: {fm.get('last_updated', 'N/A')}"
        )
        if fm.get("owner"):
            lines.append(f"   Owner: {fm.get('owner')}")

    return "\n".join(lines)


def format_json_output(tasks: List[Tuple[Path, Dict[str, Any]]]) -> str:
    """Format tasks as JSON."""
    result = []
    for path, fm in tasks:
        rel_path = str(path.relative_to(ROOT))
        result.append({"path": rel_path, "frontmatter": fm})
    return json.dumps(result, indent=2)


def format_paths(tasks: List[Tuple[Path, Dict[str, Any]]]) -> str:
    """Format tasks as simple path list."""
    if not tasks:
        return "No tasks found matching filters."
    return "\n".join(str(path.relative_to(ROOT)) for path, _ in tasks)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Filter tasks by frontmatter fields",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Filter arguments
    ap.add_argument(
        "--priority",
        action="append",
        choices=sorted(ALLOWED_PRIORITIES),
        help="Filter by priority (can specify multiple)",
    )
    ap.add_argument(
        "--status",
        action="append",
        choices=sorted(ALLOWED_STATUSES),
        help="Filter by status (can specify multiple)",
    )
    ap.add_argument(
        "--domain",
        action="append",
        choices=sorted(ALLOWED_DOMAINS),
        help="Filter by domain (can specify multiple)",
    )
    ap.add_argument("--service", action="append", help="Filter by service (can specify multiple)")
    ap.add_argument("--program", action="append", help="Filter by program (can specify multiple)")
    ap.add_argument("--owner", action="append", help="Filter by owner (can specify multiple)")

    # Date filters
    ap.add_argument("--created-after", help="Filter tasks created after date (YYYY-MM-DD)")
    ap.add_argument("--created-before", help="Filter tasks created before date (YYYY-MM-DD)")
    ap.add_argument("--updated-after", help="Filter tasks updated after date (YYYY-MM-DD)")
    ap.add_argument(
        "--updated-last-days",
        type=int,
        help="Filter tasks updated in last N days",
    )

    # Output options
    ap.add_argument(
        "--format",
        choices=["table", "list", "json", "paths"],
        default="table",
        help="Output format (default: table)",
    )
    ap.add_argument(
        "--sort",
        action="append",
        choices=["priority", "created", "updated", "title", "status", "domain", "service"],
        help="Sort by field (can specify multiple, applied in order)",
    )
    ap.add_argument(
        "--include-archive",
        action="store_true",
        help="Include archived tasks (excluded by default)",
    )
    ap.add_argument("--count-only", action="store_true", help="Only show count of matching tasks")

    args = ap.parse_args(argv)

    # Convert filter lists to sets
    priorities = set(args.priority or [])
    statuses = set(args.status or [])
    domains = set(args.domain or [])
    services = set(args.service or [])
    programs = set(args.program or [])
    owners = set(args.owner or [])

    # Parse date filters
    created_after = parse_date(args.created_after) if args.created_after else None
    created_before = parse_date(args.created_before) if args.created_before else None
    updated_after = parse_date(args.updated_after) if args.updated_after else None

    # Collect matching tasks
    matching_tasks: List[Tuple[Path, Dict[str, Any]]] = []

    for p in TASKS_DIR.rglob("*.md"):
        if should_exclude_file(p, args.include_archive):
            continue

        fm, _ = read_front_matter(p)
        if not fm:
            continue

        if matches_filters(
            fm,
            priorities,
            statuses,
            domains,
            services,
            programs,
            owners,
            created_after,
            created_before,
            updated_after,
            args.updated_last_days,
        ):
            matching_tasks.append((p, fm))

    # Sort if requested
    if args.sort:
        matching_tasks = sort_tasks(matching_tasks, args.sort)

    # Output
    if args.count_only:
        print(f"Found {len(matching_tasks)} matching task(s)")
        return 0

    if args.format == "table":
        print(format_table(matching_tasks))
    elif args.format == "list":
        print(format_list(matching_tasks))
    elif args.format == "json":
        print(format_json_output(matching_tasks))
    elif args.format == "paths":
        print(format_paths(matching_tasks))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
