#!/usr/bin/env python3
"""Scan repository TODOs and generate grouped reports under .claude/TODOs."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

RE_TODO_WITH_TAG = re.compile(r"TODO\(\s*([^\)]+?)\s*\):?\s*(.*)")
RE_GENERIC_TODO = re.compile(r"TODO[:\s-]*(.*)")
DEFAULT_TAG = "UNSCOPED"

# Root-level directories (or path prefixes) to skip entirely
SKIP_PATH_PREFIXES = [
    ("documentation",),
    ("docs",),
    ("htmlcov",),
    ("output",),
    ("dist",),
    ("build",),
    ("coverage",),
    ("__pypackages__",),
    ("scripts", "archive"),
    ("scripts", "cj_verification", "output"),
    ("TASKS", "archive"),
]

# Directory names to skip anywhere in the tree
IGNORE_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "env",
}

SKIP_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".so",
}

TODO_DIR_RELATIVE = Path(".claude") / "TODOs"


@dataclass
class TodoEntry:
    tag: str
    file_path: Path
    line_number: int
    text: str

    def to_markdown_row(self, root: Path) -> str:
        rel_path = self.file_path.relative_to(root)
        escaped_text = self.text.replace("|", "\\|").strip()
        return f"| `{rel_path}` | {self.line_number} | {escaped_text} |"


def sanitize_tag(tag: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", tag.strip()) or DEFAULT_TAG
    return cleaned.upper()


def find_todos(root: Path, include_hidden: bool = False) -> list[TodoEntry]:
    entries: list[TodoEntry] = []
    todo_dir = (root / TODO_DIR_RELATIVE).resolve()

    for path in iter_files(root, include_hidden=include_hidden):
        if path.is_dir():
            continue
        if todo_dir in path.parents:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
        except Exception:
            continue

        for idx, line in enumerate(content.splitlines(), start=1):
            if "TODO" not in line:
                continue
            tag, text = parse_todo_line(line)
            if tag is None:
                continue
            entries.append(
                TodoEntry(
                    tag=tag,
                    file_path=path,
                    line_number=idx,
                    text=text or "(no description)",
                )
            )
    return entries


def iter_files(root: Path, include_hidden: bool = False) -> Iterable[Path]:
    for path in root.rglob("*"):
        rel_parts = path.relative_to(root).parts

        if should_skip_by_prefix(rel_parts):
            continue

        if not include_hidden and any(
            part.startswith(".") and part not in {".", "..", ".claude"} for part in rel_parts
        ):
            continue

        if rel_parts and rel_parts[0] == ".claude":
            if len(rel_parts) == 1:
                continue
            allowed = rel_parts[1] in {"tasks", "TODOs"}
            if not allowed:
                continue
            if rel_parts[1] == "TODOs":
                continue

        if path.is_dir() and path.name in IGNORE_DIR_NAMES:
            continue

        if path.is_file() and path.suffix in SKIP_SUFFIXES:
            continue

        yield path


def should_skip_by_prefix(parts: tuple[str, ...] | tuple) -> bool:
    if not parts:
        return False
    for prefix in SKIP_PATH_PREFIXES:
        if len(parts) < len(prefix):
            continue
        if all(parts[i] == prefix[i] for i in range(len(prefix))):
            return True
    return False


def parse_todo_line(line: str) -> tuple[str | None, str]:
    line_stripped = line.strip()
    if not is_comment_like(line_stripped):
        return None, ""
    tagged = RE_TODO_WITH_TAG.search(line_stripped)
    if tagged:
        tag = sanitize_tag(tagged.group(1))
        text = tagged.group(2).strip()
        return tag, text

    generic = RE_GENERIC_TODO.search(line_stripped)
    if generic:
        return DEFAULT_TAG, generic.group(1).strip()

    return None, ""


def is_comment_like(line: str) -> bool:
    COMMENT_PREFIXES = ("#", "//", "/*", "<!--")
    return any(line.startswith(prefix) for prefix in COMMENT_PREFIXES)


def write_reports(root: Path, entries: list[TodoEntry]) -> None:
    todo_dir = root / TODO_DIR_RELATIVE
    todo_dir.mkdir(parents=True, exist_ok=True)

    for existing in todo_dir.glob("*.md"):
        existing.unlink()

    grouped: dict[str, list[TodoEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.tag].append(entry)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")

    summary_rows = []
    for tag in sorted(grouped):
        rows = grouped[tag]
        rows.sort(key=lambda e: (str(e.file_path), e.line_number))
        report_path = todo_dir / f"{tag}.md"
        with report_path.open("w", encoding="utf-8") as fh:
            fh.write(f"# TODO report – {tag}\n\n")
            fh.write(f"Generated: {timestamp}\n\n")
            fh.write("| File | Line | Note |\n")
            fh.write("| --- | --- | --- |\n")
            for row in rows:
                fh.write(f"{row.to_markdown_row(root)}\n")
        summary_rows.append((tag, len(rows)))

    summary_path = todo_dir / "README.md"
    with summary_path.open("w", encoding="utf-8") as summary:
        summary.write("# Repository TODO Summary\n\n")
        summary.write(f"Generated: {timestamp}\n\n")
        if not summary_rows:
            summary.write("No TODO markers found.\n")
            return
        summary.write("| Tag | Count | Report |\n")
        summary.write("| --- | --- | --- |\n")
        for tag, count in sorted(summary_rows):
            file_name = f"{tag}.md"
            summary.write(f"| {tag} | {count} | [link]({file_name}) |\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate grouped TODO reports.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (defaults to project root)",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden directories (except .claude/TODOs)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    if not root.exists():
        print(f"Root path {root} does not exist", file=sys.stderr)
        return 1

    entries = find_todos(root, include_hidden=args.include_hidden)
    write_reports(root, entries)
    print(f"Found {len(entries)} TODO items across {len({e.tag for e in entries})} tags.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
