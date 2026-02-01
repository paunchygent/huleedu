#!/usr/bin/env python3
"""
Archive a TASKS markdown file by moving it to archive/YYYY/MM/{domain}/ and updating status.

Optionally uses `git mv` if --git is provided and git is available.
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from pydantic import ValidationError

from scripts.schemas.task_schema import (
    TaskFrontmatter,
    TaskStatus,
)
from scripts.utils.frontmatter_utils import (
    read_front_matter,
)
from scripts.utils.frontmatter_utils import (
    write_front_matter as write_front_matter_file,
)

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "TASKS"

essential_keys = (
    "title",
    "status",
    "priority",
    "domain",
    "owner_team",
    "created",
    "last_updated",
)


def write_front_matter(p: Path, fm: Dict[str, Any], body: str) -> None:
    try:
        TaskFrontmatter.model_validate(fm)
    except ValidationError as e:
        errors = "; ".join(
            f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()
        )
        raise ValueError(f"Frontmatter validation failed for {p}: {errors}") from e
    write_front_matter_file(p, fm, body)


def move_file(src: Path, dest: Path, use_git: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if use_git:
        try:
            subprocess.run(["git", "mv", str(src), str(dest)], check=True)
            return
        except Exception:
            # Fall back to shutil
            pass
    shutil.move(str(src), str(dest))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Archive a TASKS markdown file")
    ap.add_argument(
        "--path",
        required=True,
        help="Path to a TASKS markdown file (absolute or repo-relative)",
    )
    ap.add_argument("--git", action="store_true", help="Use git mv if available")
    args = ap.parse_args(argv)

    src = Path(args.path)
    if not src.is_absolute():
        src = (ROOT / args.path).resolve()
    if not src.exists():
        print(f"Not found: {src}", file=sys.stderr)
        return 2

    fm, body = read_front_matter(src)
    domain = fm.get("domain") or "misc"
    today = dt.date.today()
    dest_dir = TASKS_DIR / "archive" / f"{today:%Y}" / f"{today:%m}" / domain
    dest = dest_dir / src.name

    move_file(src, dest, use_git=args.git)

    # Update front matter if present
    if fm:
        fm["status"] = TaskStatus.archived.value
        fm["last_updated"] = today.isoformat()
        write_front_matter(dest, fm, body)

    rel = dest.relative_to(ROOT)
    print(f"Archived to {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
