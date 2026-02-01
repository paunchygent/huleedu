#!/usr/bin/env python3
"""
Migrate TASKS frontmatter statuses to TASKS lifecycle v2.

Rules:
- status: research  -> proposed
- status: completed -> done

Also repairs known legacy omissions:
- Add missing "type" (defaults to "task", or "programme" for HUB.md).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from scripts.schemas.task_schema import TaskFrontmatter
from scripts.utils.frontmatter_utils import read_front_matter, write_front_matter

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "TASKS"

EXCLUDED_FILES = {
    "_REORGANIZATION_PROPOSAL.md",
    "INDEX.md",
    "TASK_INDEX.md",
}


def should_skip(path: Path) -> bool:
    if path.name in EXCLUDED_FILES:
        return True
    return False


def infer_type(path: Path, fm: dict[str, Any]) -> str:
    existing = str(fm.get("type", "")).strip()
    if existing:
        return existing
    if path.name == "HUB.md":
        return "programme"
    return "task"


def migrate_file(path: Path, today: str) -> tuple[bool, dict[str, Any]]:
    fm, body = read_front_matter(path)
    if not fm:
        return False, {}

    changed = False

    new_type = infer_type(path, fm)
    if fm.get("type") != new_type:
        fm["type"] = new_type
        changed = True

    status = str(fm.get("status", "")).strip()
    if status == "research":
        fm["status"] = "proposed"
        changed = True
    elif status == "completed":
        fm["status"] = "done"
        changed = True

    if changed:
        fm["last_updated"] = today

        # Validate against schema to catch enum issues early.
        try:
            TaskFrontmatter.model_validate(fm)
        except ValidationError as e:
            errors = "; ".join(
                f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()
            )
            raise ValueError(f"Frontmatter validation failed for {path}: {errors}") from e

        write_front_matter(path, fm, body)

    return changed, fm


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Migrate TASKS statuses to lifecycle v2")
    ap.add_argument("--root", default=str(TASKS_DIR), help="TASKS root directory")
    ap.add_argument(
        "--write",
        action="store_true",
        help="Apply changes (default: dry-run and report only)",
    )
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"Error: TASKS root does not exist: {root}", file=sys.stderr)
        return 2

    today = dt.date.today().isoformat()

    candidates = [p for p in root.rglob("*.md") if p.is_file() and not should_skip(p)]
    changed_paths: list[str] = []

    for p in sorted(candidates):
        fm, body = read_front_matter(p)
        if not fm:
            continue

        status = str(fm.get("status", "")).strip()
        has_missing_type = "type" not in fm or not str(fm.get("type", "")).strip()
        would_change = has_missing_type or status in {"research", "completed"}
        if not would_change:
            continue

        rel = str(p.relative_to(ROOT))

        if not args.write:
            changed_paths.append(rel)
            continue

        migrated, _ = migrate_file(p, today=today)
        if migrated:
            changed_paths.append(rel)

    if not args.write:
        print(f"Dry-run: would update {len(changed_paths)} file(s).")
        for rel in changed_paths[:50]:
            print(f"- {rel}")
        if len(changed_paths) > 50:
            print(f"... (+{len(changed_paths) - 50} more)")
        return 0

    print(f"Updated {len(changed_paths)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
