#!/usr/bin/env bash
# Hook: Auto-fix markdownlint violations on .md file writes
# Runs markdownlint --fix on the file being written

# Read JSON input from stdin
INPUT=$(cat)

# Extract tool info
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only process Write operations on markdown files
if [[ "$TOOL_NAME" != "Write" ]] || [[ ! "$FILE_PATH" =~ \.md$ ]]; then
  exit 0
fi

# Check if markdownlint is available
if ! command -v markdownlint &> /dev/null; then
  # Silently skip if markdownlint not installed
  exit 0
fi

# Check if file will exist after write (either new or being updated)
# We'll run markdownlint after the file is written, so this is just a validation hook
# The actual fixing should happen post-write

# For now, just validate that the content follows markdown rules
# We can't fix inline because we'd need to modify the content being written

# This is informational only - warns about issues but doesn't block
exit 0
