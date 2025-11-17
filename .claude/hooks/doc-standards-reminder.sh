#!/usr/bin/env bash
# Hook: Show documentation standards on first doc file creation per session

# Get the file path being written from the tool input
FILE_PATH="${CLAUDE_TOOL_INPUT_file_path:-}"

# Check if this is a documentation file (in .claude/, docs/, or TASKS/)
# Matches both absolute paths and relative paths
if [[ "$FILE_PATH" =~ \.claude/ ]] || \
   [[ "$FILE_PATH" =~ /docs/ ]] || \
   [[ "$FILE_PATH" =~ /TASKS/ ]] || \
   [[ "$FILE_PATH" =~ ^docs/ ]] || \
   [[ "$FILE_PATH" =~ ^TASKS/ ]]; then

  # Use a session-specific marker file
  # We use CLAUDE_SESSION_ID if available, or create a simple per-day marker
  SESSION_MARKER="/tmp/claude_doc_reminder_$(date +%Y%m%d)_${CLAUDE_SESSION_ID:-default}"

  # Check if we've already shown the reminder this session
  if [[ ! -f "$SESSION_MARKER" ]]; then
    # Mark that we've shown it
    touch "$SESSION_MARKER"

    # Output the documentation standards to stderr (appears as a message to Claude)
    cat >&2 << 'EOF'
📋 DOCUMENTATION STANDARDS REMINDER

You are creating a file in a documentation directory (.claude/, docs/, or TASKS/).

Please review the documentation standards:

EOF

    # Output the actual standards file
    if [[ -f "$CLAUDE_PROJECT_DIR/.claude/rules/090-documentation-standards.md" ]]; then
      cat "$CLAUDE_PROJECT_DIR/.claude/rules/090-documentation-standards.md" >&2
    else
      echo "⚠️  Could not find documentation standards file at:" >&2
      echo "   $CLAUDE_PROJECT_DIR/.claude/rules/090-documentation-standards.md" >&2
    fi

    cat >&2 << 'EOF'

────────────────────────────────────────────────────────────────
EOF
  fi
fi

# Always exit 0 to allow the write operation
exit 0
