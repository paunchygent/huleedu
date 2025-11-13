#!/usr/bin/env python3
"""
Generate TASKS/INDEX.md summarizing tasks by domain, status, and programme.
No external dependencies; parses simple front matter only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "TASKS"
INDEX_FILE = TASKS_DIR / "INDEX.md"

ALLOWED_DOMAINS = [
    "assessment", "content", "identity", "frontend", "infrastructure",
    "security", "integrations", "architecture"
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
            items = [i.strip().strip("'\"") for i in v[1:-1].split(",") if i.strip()]
            data[k] = items
        else:
            data[k] = v.strip("'\"")
    return data, body


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(TASKS_DIR))
    ap.add_argument("--out", default=str(INDEX_FILE))
    ap.add_argument(
        "--include-archive",
        action="store_true",
        help="Include archive in index",
    )
    ap.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit nonzero if any file lacks front matter",
    )
    args = ap.parse_args(argv)

    root = Path(args.root)
    out = Path(args.out)

    by_domain = defaultdict(list)
    by_status = defaultdict(list)
    by_program = defaultdict(list)
    missing_meta = []

    for p in root.rglob("*.md"):
        if not args.include_archive and "archive" in p.parts:
            continue
        if p.name.upper() in {"INDEX.MD", "_REORGANIZATION_PROPOSAL.MD", "_INVENTORY_ANALYSIS.MD"}:
            continue
        fm, _ = read_front_matter(p)
        rel = p.relative_to(ROOT)
        if not fm:
            missing_meta.append(str(rel))
            continue
        domain = fm.get("domain", "unknown")
        status = fm.get("status", "unknown")
        program = fm.get("program", "")
        title = fm.get("title", p.stem)
        by_domain[domain].append((title, status, str(rel)))
        by_status[status].append((title, domain, str(rel)))
        if program:
            by_program[program].append((title, domain, status, str(rel)))

    # Compose markdown
    lines = []
    lines.append("# TASKS Index")
    lines.append("")
    lines.append(f"Generated: {dt.datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    # Summary counts
    total = sum(len(v) for v in by_domain.values())
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total tasks indexed: {total}")
    for d in ALLOWED_DOMAINS:
        lines.append(f"- {d}: {len(by_domain.get(d, []))}")
    other_domains = [k for k in by_domain.keys() if k not in ALLOWED_DOMAINS]
    if other_domains:
        other_count = sum(len(by_domain[k]) for k in other_domains)
        other_list = ", ".join(other_domains)
        lines.append(f"- other: {other_count} ({other_list})")
    lines.append("")

    # By Domain
    lines.append("## By Domain")
    for d in ALLOWED_DOMAINS + other_domains:
        items = sorted(by_domain.get(d, []), key=lambda x: x[0].lower())
        lines.append(f"\n### {d} ({len(items)})")
        if not items:
            lines.append("- (none)")
            continue
        for title, status, rel in items:
            lines.append(f"- [{title}]({rel}) — `{status}`")

    # By Status
    lines.append("\n## By Status")
    for status, items in sorted(by_status.items()):
        items = sorted(items, key=lambda x: x[0].lower())
        lines.append(f"\n### {status} ({len(items)})")
        for title, domain, rel in items:
            lines.append(f"- [{title}]({rel}) — `{domain}`")

    # By Programme
    lines.append("\n## By Programme")
    if not by_program:
        lines.append("- (none)")
    else:
        for program, items in sorted(by_program.items()):
            items = sorted(items, key=lambda x: x[0].lower())
            lines.append(f"\n### {program} ({len(items)})")
            for title, domain, status, rel in items:
                lines.append(f"- [{title}]({rel}) — `{domain}` · `{status}`")

    if missing_meta:
        lines.append("\n## Files Missing Front Matter")
        for rel in sorted(missing_meta):
            lines.append(f"- {rel}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)}")

    if args.fail_on_missing and missing_meta:
        print("Missing front matter detected.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
