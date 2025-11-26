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
import re
import sys
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]  # repo root
# Ensure repo root is importable when running via `python scripts/...`
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts.task_mgmt.task_frontmatter_schema import (  # noqa: E402
    TaskDomain,
    TaskFrontmatter,
    TaskPriority,
    TaskStatus,
)

TASKS_DIR = ROOT / "TASKS"


def slugify(text: str) -> str:
    text = text.strip()
    text = re.sub(r"[\s/]+", "-", text)
    text = re.sub(r"[^A-Za-z0-9_-]+", "", text)
    return text.lower().strip("-")


def build_path(domain: str, program: str | None, filename: str) -> Path:
    if program:
        return TASKS_DIR / "programmes" / program / filename
    return TASKS_DIR / domain / filename


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Create a new task document")
    p.add_argument("--title", required=True, help="Human title for the task")
    p.add_argument("--domain", required=True, choices=sorted([d.value for d in TaskDomain]))
    p.add_argument("--program", help="Optional programme bucket (e.g., cj_confidence)")
    p.add_argument("--service", help="Optional service slug (e.g., nlp_lang_tool_service)")
    p.add_argument(
        "--status", default=TaskStatus.research.value, choices=[s.value for s in TaskStatus]
    )
    p.add_argument(
        "--priority", default=TaskPriority.medium.value, choices=[p.value for p in TaskPriority]
    )
    p.add_argument("--owner-team", default="agents", dest="owner_team")
    p.add_argument("--owner", default="", help="Optional owner handle like @me")
    p.add_argument("--id", default="", help="Optional external ID like TASK-052")
    p.add_argument("--filename", help="Optional explicit filename (relative)")

    args = p.parse_args(argv)

    today = dt.date.today().isoformat()

    if args.filename:
        fn = args.filename
        default_id = Path(fn).stem.lower()
    else:
        slug = slugify(args.title)
        fn = f"{slug}.md"
        default_id = slug

    dest = build_path(args.domain, args.program, fn)

    if dest.exists():
        print(f"Error: {dest} already exists", file=sys.stderr)
        return 2

    dest.parent.mkdir(parents=True, exist_ok=True)

    fm_dict = {
        "id": args.id or default_id,
        "title": args.title,
        "type": "task",
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

    # Validate with Pydantic to catch enum typos early
    try:
        TaskFrontmatter.model_validate(fm_dict)
    except ValidationError as e:
        print("Frontmatter validation failed:", file=sys.stderr)
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"])
            print(f"  {loc}: {err['msg']}", file=sys.stderr)
        return 1

    frontmatter_lines = ["---"]
    for k, v in fm_dict.items():
        if isinstance(v, list):
            sv = "[" + ", ".join(repr(x) for x in v) + "]"
        else:
            sv = repr(v)
        frontmatter_lines.append(f"{k}: {sv}")
    frontmatter_lines.append("---")

    body = "\n".join(
        frontmatter_lines
        + [
            f"# {args.title}",
            "",
            "## Objective",
            "",
            "[What are we trying to achieve?]",
            "",
            "## Context",
            "",
            "[Why is this needed?]",
            "",
            "## Plan",
            "",
            "[Key steps]",
            "",
            "## Success Criteria",
            "",
            "[How do we know it's done?]",
            "",
            "## Related",
            "",
            "[List related tasks or docs]",
            "",
        ]
    )

    dest.write_text(body, encoding="utf-8")
    print(f"Created {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
