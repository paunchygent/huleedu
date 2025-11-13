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
}
ALLOWED_STATUSES = {"research", "blocked", "in_progress", "completed", "paused", "archived"}
ALLOWED_PRIORITIES = {"low", "medium", "high", "critical"}

FRONT_MATTER_REQUIRED = [
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


def validate_file(p: Path, strict: bool = False) -> list[str]:
    errors: list[str] = []
    fm, _ = read_front_matter(p)
    if not fm:
        errors.append("missing front matter")
        return errors

    for key in FRONT_MATTER_REQUIRED:
        if key not in fm or not str(fm[key]).strip():
            errors.append(f"missing required '{key}'")

    if fm.get("domain") not in ALLOWED_DOMAINS:
        errors.append(f"invalid domain '{fm.get('domain')}'")
    if fm.get("status") not in ALLOWED_STATUSES:
        errors.append(f"invalid status '{fm.get('status')}'")
    if fm.get("priority") not in ALLOWED_PRIORITIES:
        errors.append(f"invalid priority '{fm.get('priority')}'")

    # Dates
    for key in ("created", "last_updated"):
        val = str(fm.get(key, ""))
        try:
            dt.date.fromisoformat(val)
        except ValueError:
            errors.append(f"invalid date '{key}': '{val}' (expected YYYY-MM-DD)")

    # Owner team default
    if not fm.get("owner_team"):
        errors.append("owner_team must be set (e.g., 'agents')")

    return errors


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(TASKS_DIR), help="Tasks root directory")
    ap.add_argument("--exclude-archive", action="store_true", default=True)
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root)
    failures = 0
    for p in root.rglob("*.md"):
        if "archive" in p.parts and args.exclude_archive:
            continue
        rel = p.relative_to(ROOT)
        errs = validate_file(p)
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
