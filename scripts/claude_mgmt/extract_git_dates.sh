#!/bin/bash
# Extract git created and last_updated dates for all rule files
# Handles historical moves and renames:
#   .cursor/rules/*.mdc -> .claude/rules/*.mdc (2025-09-10)
#   .claude/rules/*.mdc -> .claude/rules/*.md (2025-11-17)

echo "rule_id|created|last_updated"
echo "------|-------|------------"

for file in .claude/rules/*.md; do
  if [ "$(basename "$file")" != "README.md" ]; then
    rule_id=$(basename "$file" .md)
    basename_file=$(basename "$file")

    # Check all historical locations:
    # 1. Current: .claude/rules/*.md
    # 2. Previous: .claude/rules/*.mdc
    # 3. Original: .cursor/rules/*.mdc
    created=$(git log --all --reverse --format=%ad --date=short -- \
      "$file" \
      "${file%.md}.mdc" \
      ".cursor/rules/${basename_file%.md}.mdc" \
      2>/dev/null | head -1)

    # Last updated is the most recent commit to any location
    updated=$(git log -1 --all --format=%ad --date=short -- \
      "$file" \
      "${file%.md}.mdc" \
      ".cursor/rules/${basename_file%.md}.mdc" \
      2>/dev/null)

    echo "$rule_id|$created|$updated"
  fi
done
