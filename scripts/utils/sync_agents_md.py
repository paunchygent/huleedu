#!/usr/bin/env python3
"""
Sync AGENTS.md content to CLAUDE.md, CODEX.md, and GEMINI.md.

This ensures all AI assistant instruction files have identical content,
sourced from the canonical AGENTS.md file.
"""

import sys
from pathlib import Path


def sync_file(source_path: Path, target_path: Path) -> bool:
    """
    Synchronize content from source to target file.

    Returns:
        True if file was changed, False if already in sync
    """
    try:
        with open(source_path, "r", encoding="utf-8") as f:
            source_content = f.read()
    except FileNotFoundError:
        print(f"❌ Error: Source file not found: {source_path}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading source file {source_path}: {e}")
        sys.exit(1)

    # Normalize content: strip trailing whitespace and ensure single trailing newline
    normalized_content = source_content.rstrip()
    if normalized_content:
        normalized_content += "\n"

    # Read existing target content if it exists
    target_content = ""
    file_existed = target_path.exists()
    if file_existed:
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                target_content = f.read()
        except Exception as e:
            print(f"⚠️  Error reading {target_path}: {e}")
            target_content = "<read_error>"

    # Check if update is needed
    has_changed = target_content != normalized_content

    # Write normalized content
    try:
        with open(target_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(normalized_content)

        if has_changed:
            action = "Updated" if file_existed else "Created"
            print(f"✅ {action} {target_path.name}")
        else:
            print(f"✨ {target_path.name} already in sync")

        return has_changed
    except Exception as e:
        print(f"❌ Error writing to {target_path}: {e}")
        sys.exit(1)


def main():
    """Sync AGENTS.md to all AI assistant instruction files."""
    repo_root = Path(__file__).resolve().parents[2]
    source_file = repo_root / "AGENTS.md"

    target_files = [
        repo_root / "CODEX.md",
        repo_root / "GEMINI.md",
        # CLAUDE.md excluded - now uses .claude/rules/ for Claude Code native memory
    ]

    print("🔄 Syncing AGENTS.md to AI assistant files...")

    any_changed = False
    for target in target_files:
        changed = sync_file(source_file, target)
        any_changed = any_changed or changed

    print("🏁 Sync complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
