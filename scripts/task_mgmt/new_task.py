#!/usr/bin/env python3
"""
Scaffold a new TASKS markdown file with minimal YAML front matter and a standard body template.
Usage examples:
  python scripts/task_mgmt/new_task.py --title "Svelte 5 + Vite CORS" \
    --domain frontend
  python scripts/task_mgmt/new_task.py --title "CJ Phase 3 Hub" \
    --program cj_confidence --domain assessment
  python scripts/task_mgmt/new_task.py --title "AI Feedback Service" \
    --domain assessment --service ai_feedback_service --priority high
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[2]  # repo root
TASKS_DIR = ROOT / "TASKS"


def slugify(text: str) -> str:
    text = text.strip()
    text = re.sub(r"[\s/]+", "-", text)
    text = re.sub(r"[^A-Za-z0-9_-]+", "", text)
    return text.lower().strip("-")


def caps_filename(title: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", title.strip()).strip("_")
    return f"{s.upper()}.md"


def build_path(domain: str, program: str | None, filename: str) -> Path:
    if program:
        return TASKS_DIR / "programmes" / program / filename
    return TASKS_DIR / domain / filename


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Create a new task document")
    p.add_argument("--title", required=True, help="Human title for the task")
    p.add_argument("--domain", required=True, choices=sorted(ALLOWED_DOMAINS))
    p.add_argument("--program", help="Optional programme bucket (e.g., cj_confidence)")
    p.add_argument("--service", help="Optional service slug (e.g., nlp_lang_tool_service)")
    p.add_argument("--status", default="research", choices=sorted(ALLOWED_STATUSES))
    p.add_argument("--priority", default="medium", choices=sorted(ALLOWED_PRIORITIES))
    p.add_argument("--owner-team", default="agents", dest="owner_team")
    p.add_argument("--owner", default="", help="Optional owner handle like @me")
    p.add_argument("--id", default="", help="Optional external ID like TASK-052")
    p.add_argument("--filename", help="Optional explicit filename (relative)")

    args = p.parse_args(argv)

    today = dt.date.today().isoformat()
    fn = args.filename or caps_filename(args.title)
    dest = build_path(args.domain, args.program, fn)

    if dest.exists():
        print(f"Error: {dest} already exists", file=sys.stderr)
        return 2

    dest.parent.mkdir(parents=True, exist_ok=True)

    fm = {
        "id": args.id or "",
        "title": args.title,
        "status": args.status,
        "priority": args.priority,
        "domain": args.domain,
        "service": args.service or "",
        "owner_team": args.owner_team,
        "owner": args.owner or "",
        "program": args.program or "",
        "created": today,
        "last_updated": today,
        "related": [],
        "labels": [],
    }

    body = f"""---
{os.linesep.join(f"{k}: {v!r}" for k, v in fm.items())}
---
# {args.title}

## Objective

[What are we trying to achieve?]

## Context

[Why is this needed?]

## Plan

[Key steps]

## Success Criteria

[How do we know it's done?]

## Related

[List related tasks or docs]
"""

    dest.write_text(body, encoding="utf-8")
    print(f"Created {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
