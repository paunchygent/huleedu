# Claude Code Hooks Examples

Real-world examples of Claude Code hooks for various use cases.

## Example 1: Documentation Standards Reminder

**Use case:** Show documentation standards when creating files in `.claude/`, `docs/`, or `TASKS/`

**Hook type:** PreToolUse
**File:** `.claude/hooks/doc-standards-reminder.sh`

```bash
#!/usr/bin/env bash
# Hook: Show documentation standards on first doc file creation per session

# Get the file path being written from the tool input
FILE_PATH="${CLAUDE_TOOL_INPUT_file_path:-}"

# Check if this is a documentation file
if [[ "$FILE_PATH" =~ \.claude/ ]] || \
   [[ "$FILE_PATH" =~ /docs/ ]] || \
   [[ "$FILE_PATH" =~ /TASKS/ ]] || \
   [[ "$FILE_PATH" =~ ^docs/ ]] || \
   [[ "$FILE_PATH" =~ ^TASKS/ ]]; then

  # Use a session-specific marker file
  SESSION_MARKER="/tmp/claude_doc_reminder_$(date +%Y%m%d)_${CLAUDE_SESSION_ID:-default}"

  # Check if we've already shown the reminder this session
  if [[ ! -f "$SESSION_MARKER" ]]; then
    # Mark that we've shown it
    touch "$SESSION_MARKER"

    # Output the documentation standards
    cat >&2 << 'EOF'
📋 DOCUMENTATION STANDARDS REMINDER

You are creating a file in a documentation directory.
Please review the documentation standards at:
.claude/rules/090-documentation-standards.md

EOF

    if [[ -f "$CLAUDE_PROJECT_DIR/.claude/rules/090-documentation-standards.md" ]]; then
      cat "$CLAUDE_PROJECT_DIR/.claude/rules/090-documentation-standards.md" >&2
    fi

    cat >&2 << 'EOF'
────────────────────────────────────────────────────────────────
EOF
  fi
fi

# Always exit 0 to allow the write operation
exit 0
```

**Configuration:**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/doc-standards-reminder.sh"
          }
        ]
      }
    ]
  }
}
```

## Example 2: Protect Sensitive Files

**Use case:** Prevent editing or reading `.env` files, `package-lock.json`, and Git files

**Hook type:** PreToolUse
**File:** `.claude/hooks/protect-files.py`

```python
#!/usr/bin/env python3
"""
PreToolUse hook to protect sensitive files from modification.
"""
import json
import sys

PROTECTED_PATTERNS = [
    '.env',
    'package-lock.json',
    'yarn.lock',
    'pnpm-lock.yaml',
    '.git/',
    'node_modules/',
]

ALLOWED_EXCEPTIONS = [
    '.env.sample',
    '.env.example',
]

def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)  # Allow on JSON error

    tool_name = input_data.get('tool_name', '')
    tool_input = input_data.get('tool_input', {})

    # Only check file operations
    if tool_name not in ['Read', 'Edit', 'Write', 'MultiEdit']:
        sys.exit(0)

    file_path = tool_input.get('file_path', '')

    # Check if file is protected
    for pattern in PROTECTED_PATTERNS:
        if pattern in file_path:
            # Check for exceptions
            if any(exc in file_path for exc in ALLOWED_EXCEPTIONS):
                continue

            print(f"🚫 BLOCKED: Access to protected file pattern '{pattern}'", file=sys.stderr)
            print(f"   File: {file_path}", file=sys.stderr)
            print(f"   Tool: {tool_name}", file=sys.stderr)
            sys.exit(2)

    # Allow operation
    sys.exit(0)

if __name__ == '__main__':
    main()
```

**Configuration:**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/protect-files.py"
          }
        ]
      }
    ]
  }
}
```

## Example 3: Dangerous Bash Command Blocking

**Use case:** Block dangerous bash commands like `rm -rf /`, force push, etc.

**Hook type:** PreToolUse
**File:** `.claude/hooks/bash-safety.py`

```python
#!/usr/bin/env python3
"""
PreToolUse hook to block dangerous bash commands.
"""
import json
import sys
import re

DANGEROUS_PATTERNS = [
    (r'\brm\s+-rf\s+/', "Recursive deletion from root"),
    (r'\brm\s+.*-[a-z]*r[a-z]*f', "Dangerous rm -rf pattern"),
    (r'\bgit\s+push\s+--force', "Force push (use --force-with-lease instead)"),
    (r'\bgit\s+reset\s+--hard', "Hard reset (data loss risk)"),
    (r'\bdd\s+if=', "dd command (data destruction risk)"),
    (r'\b>\s*/dev/', "Writing to /dev/ (system risk)"),
    (r'\bchmod\s+777', "chmod 777 (security risk)"),
]

def is_dangerous_command(command):
    """Check if command matches any dangerous pattern."""
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True, reason
    return False, None

def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = input_data.get('tool_name', '')

    if tool_name != 'Bash':
        sys.exit(0)

    tool_input = input_data.get('tool_input', {})
    command = tool_input.get('command', '')

    is_dangerous, reason = is_dangerous_command(command)

    if is_dangerous:
        print(f"🚫 BLOCKED: {reason}", file=sys.stderr)
        print(f"   Command: {command}", file=sys.stderr)
        print(f"   Consider using a safer alternative", file=sys.stderr)
        sys.exit(2)

    sys.exit(0)

if __name__ == '__main__':
    main()
```

**Configuration:**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/bash-safety.py"
          }
        ]
      }
    ]
  }
}
```

## Example 4: Auto-format Python Files

**Use case:** Automatically run `ruff format` on Python files after editing

**Hook type:** PostToolUse
**File:** `.claude/hooks/format-python.sh`

```bash
#!/usr/bin/env bash
# PostToolUse hook to format Python files with ruff

FILE_PATH="${CLAUDE_TOOL_INPUT_file_path:-}"

# Only process .py files
if [[ "$FILE_PATH" =~ \.py$ ]]; then
    # Format with ruff
    ruff format "$FILE_PATH" 2>&1

    if [ $? -eq 0 ]; then
        echo "✅ Formatted Python file: $FILE_PATH" >&2
    else
        echo "⚠️  Could not format: $FILE_PATH" >&2
    fi
fi

exit 0
```

**Configuration:**
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/format-python.sh"
          }
        ]
      }
    ]
  }
}
```

## Example 5: Log All Bash Commands

**Use case:** Keep a log of all bash commands executed by Claude

**Hook type:** PreToolUse
**File:** `.claude/hooks/log-bash.sh`

```bash
#!/usr/bin/env bash
# PreToolUse hook to log all bash commands

LOG_FILE="$HOME/.claude/bash-command-log.txt"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Get command and description
COMMAND="${CLAUDE_TOOL_INPUT_command:-}"
DESCRIPTION="${CLAUDE_TOOL_INPUT_description:-No description}"

# Log with timestamp
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $DESCRIPTION" >> "$LOG_FILE"
echo "  Command: $COMMAND" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Always approve
exit 0
```

**Configuration:**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/log-bash.sh"
          }
        ]
      }
    ]
  }
}
```

## Example 6: Send Notifications on Completion

**Use case:** Send a notification when Claude stops working

**Hook type:** Stop
**File:** `.claude/hooks/notify-stop.sh`

```bash
#!/usr/bin/env bash
# Stop hook to send notification when Claude finishes

NTFY_URL="https://ntfy.sh/your-channel"

# Send notification
curl -s -H "Title: Claude Code Complete" \
     -H "Priority: low" \
     -d "Claude has finished working on your task" \
     "$NTFY_URL" > /dev/null 2>&1

# Continue (don't block)
exit 0
```

**Configuration:**
```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/notify-stop.sh"
          }
        ]
      }
    ]
  }
}
```

## Example 7: Validate Task Document Frontmatter

**Use case:** Ensure TASKS documents have proper frontmatter before writing

**Hook type:** PreToolUse
**File:** `.claude/hooks/validate-task-frontmatter.py`

```python
#!/usr/bin/env python3
"""
PreToolUse hook to validate TASKS document frontmatter.
"""
import json
import sys
import re

def has_valid_frontmatter(content):
    """Check if content has valid YAML frontmatter."""
    if not content.startswith('---\n'):
        return False

    parts = content.split('\n---\n', 1)
    if len(parts) != 2:
        return False

    frontmatter = parts[0][4:]  # Remove initial ---\n

    # Check for required fields
    required_fields = ['id:', 'status:', 'created:']
    return all(field in frontmatter for field in required_fields)

def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = input_data.get('tool_name', '')
    tool_input = input_data.get('tool_input', {})

    if tool_name != 'Write':
        sys.exit(0)

    file_path = tool_input.get('file_path', '')

    # Only check TASKS documents
    if not re.match(r'^TASKS/.*\.md$', file_path):
        sys.exit(0)

    # Skip index and archive
    if 'INDEX.md' in file_path or '/archive/' in file_path:
        sys.exit(0)

    content = tool_input.get('content', '')

    if not has_valid_frontmatter(content):
        print("🚫 BLOCKED: TASKS document missing valid frontmatter", file=sys.stderr)
        print(f"   File: {file_path}", file=sys.stderr)
        print("   Required fields: id, status, created", file=sys.stderr)
        sys.exit(2)

    sys.exit(0)

if __name__ == '__main__':
    main()
```

**Configuration:**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/validate-task-frontmatter.py"
          }
        ]
      }
    ]
  }
}
```

## Testing Hooks

To test a hook without Claude:

```bash
# Test with sample JSON input
echo '{
  "tool_name": "Write",
  "tool_input": {
    "file_path": ".env",
    "content": "SECRET=test"
  }
}' | .claude/hooks/protect-files.py

# Check exit code
echo $?  # Should be 2 (blocked)

# Test with approved file
echo '{
  "tool_name": "Write",
  "tool_input": {
    "file_path": "README.md",
    "content": "# Test"
  }
}' | .claude/hooks/protect-files.py

echo $?  # Should be 0 (approved)
```
