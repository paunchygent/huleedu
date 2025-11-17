#!/usr/bin/env python3
"""
Remove duplicate H1 headings from TASKS files.

When a task has a title in frontmatter and a duplicate H1 in content,
this script removes the H1 from content (keeping the frontmatter title).
"""

import re
from pathlib import Path
from typing import Optional, Tuple


def parse_frontmatter_and_content(content: str) -> Tuple[Optional[str], str, str]:
    """
    Parse frontmatter and content from markdown.

    Returns:
        (title_from_frontmatter, frontmatter_block, content_after_frontmatter)
    """
    # Match YAML frontmatter
    fm_pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    match = fm_pattern.match(content)

    if not match:
        return None, "", content

    frontmatter = match.group(1)
    content_after = content[match.end() :]
    frontmatter_block = match.group(0)

    # Extract title from frontmatter
    title_match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', frontmatter, re.MULTILINE)
    title = title_match.group(1) if title_match else None

    return title, frontmatter_block, content_after


def remove_duplicate_h1(content: str) -> Tuple[str, bool]:
    """
    Remove duplicate H1 if it matches frontmatter title.

    Returns:
        (updated_content, was_modified)
    """
    title, fm_block, content_after = parse_frontmatter_and_content(content)

    if not title:
        return content, False

    # Find first H1 in content
    h1_pattern = re.compile(r"^#\s+(.+?)$", re.MULTILINE)
    h1_match = h1_pattern.search(content_after)

    if not h1_match:
        return content, False

    h1_text = h1_match.group(1).strip()

    # Normalize for comparison (remove quotes, extra spaces)
    title_normalized = title.strip(" \"'")
    h1_normalized = h1_text.strip()

    # Check if H1 matches title (exact or very close)
    if title_normalized.lower() == h1_normalized.lower():
        # Remove the H1 line and any blank lines immediately after
        start = h1_match.start()
        end = h1_match.end()

        # Also remove trailing newlines after the H1
        while end < len(content_after) and content_after[end] == "\n":
            end += 1

        # Reconstruct content without the duplicate H1
        new_content_after = content_after[:start] + content_after[end:]

        # Remove leading blank lines from content
        new_content_after = new_content_after.lstrip("\n")

        new_content = fm_block + new_content_after
        return new_content, True

    return content, False


def process_tasks_directory(tasks_dir: Path, dry_run: bool = True) -> None:
    """
    Process all markdown files in TASKS directory.
    """
    # Find all .md files, excluding special files and archive
    md_files = [
        f
        for f in tasks_dir.rglob("*.md")
        if f.name not in ("_REORGANIZATION_PROPOSAL.md", "INDEX.md", "README.md", "HUB.md")
        and "archive" not in f.parts
    ]

    modified_count = 0
    total_count = len(md_files)

    print(f"{'DRY RUN: ' if dry_run else ''}Processing {total_count} TASKS files...\n")

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        new_content, was_modified = remove_duplicate_h1(content)

        if was_modified:
            modified_count += 1
            rel_path = md_file.relative_to(tasks_dir)

            if dry_run:
                print(f"[DRY RUN] Would modify: {rel_path}")
            else:
                md_file.write_text(new_content, encoding="utf-8")
                print(f"✓ Modified: {rel_path}")

    print(f"\n{'Would modify' if dry_run else 'Modified'} {modified_count}/{total_count} files")

    if dry_run and modified_count > 0:
        print("\nRun with --no-dry-run to apply changes")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Remove duplicate H1 headings from TASKS files")
    parser.add_argument(
        "--tasks-dir",
        type=Path,
        default=Path("TASKS"),
        help="Path to TASKS directory (default: TASKS)",
    )
    parser.add_argument(
        "--no-dry-run", action="store_true", help="Actually modify files (default is dry run)"
    )

    args = parser.parse_args()

    if not args.tasks_dir.exists():
        print(f"Error: TASKS directory not found: {args.tasks_dir}")
        return 1

    process_tasks_directory(args.tasks_dir, dry_run=not args.no_dry_run)
    return 0


if __name__ == "__main__":
    exit(main())
