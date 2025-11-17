# Claude Code Hooks Reference

Comprehensive reference for creating and configuring Claude Code hooks.

## Hook Lifecycle Events

### PreToolUse
Executes **before** a tool runs. Can block or approve operations.

**Use cases:**
- Validate file paths before edits/writes
- Block dangerous commands
- Protect sensitive files
- Enforce naming conventions

**Available data:**
```bash
CLAUDE_TOOL_NAME          # Tool being called (e.g., "Bash", "Write", "Edit")
CLAUDE_TOOL_INPUT_*       # Tool-specific inputs (command, file_path, etc.)
```

**Exit behavior:**
- Exit 0: Approve operation
- Exit 2: Block operation (show stderr as error to Claude)

### PostToolUse
Executes **after** a tool completes successfully.

**Use cases:**
- Format files after edits
- Run linters/formatters
- Send notifications
- Log operations

**Exit behavior:**
- Exit 0: Success
- Exit 2: Report failure (Claude sees stderr)

### UserPromptSubmit
Executes when user submits a prompt.

**Use cases:**
- Log prompts
- Validate prompt content
- Inject additional context
- Track usage

**Exit behavior:**
- Exit 0: Continue with prompt
- Exit 2: Block prompt submission

### Stop
Controls whether Claude should stop working.

**Use cases:**
- Check task completion criteria
- Enforce work limits
- Custom stopping logic

**Exit behavior:**
- Exit 0: Continue working
- Exit 2: Stop working

### SessionStart
Runs at session initialization.

**Use cases:**
- Load environment context
- Initialize logging
- Set up project state

## Configuration Patterns

### Basic Hook in settings.json

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/validate-file.sh"
          }
        ]
      }
    ]
  }
}
```

### Multiple Hooks (Run in Parallel)

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/format.sh"
          },
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/notify.sh"
          }
        ]
      }
    ]
  }
}
```

### Tool-Specific Matchers

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/validate-bash.py"
          }
        ]
      },
      {
        "matcher": "Write|Edit",
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

### Wildcard Matcher (All Tools)

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/log-all-tools.sh"
          }
        ]
      }
    ]
  }
}
```

## Hook Script Patterns

### Python Hook Template

```python
#!/usr/bin/env python3
"""
PreToolUse hook to validate operations.
"""
import json
import sys
import os

def main():
    # Read JSON input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("Error: Invalid JSON input", file=sys.stderr)
        sys.exit(2)

    tool_name = input_data.get('tool_name', '')
    tool_input = input_data.get('tool_input', {})

    # Validation logic
    if tool_name == 'Write':
        file_path = tool_input.get('file_path', '')

        # Block sensitive files
        if '.env' in file_path and not file_path.endswith('.env.sample'):
            print(f"BLOCKED: Cannot write to {file_path}", file=sys.stderr)
            sys.exit(2)

    # Approve
    sys.exit(0)

if __name__ == '__main__':
    main()
```

### Bash Hook Template

```bash
#!/usr/bin/env bash
# PostToolUse hook to format files

# Get file path from tool input
FILE_PATH="${CLAUDE_TOOL_INPUT_file_path:-}"

# Only process .md files
if [[ "$FILE_PATH" =~ \.md$ ]]; then
    # Format the file
    prettier --write "$FILE_PATH" 2>&1

    if [ $? -eq 0 ]; then
        echo "✅ Formatted: $FILE_PATH" >&2
        exit 0
    else
        echo "⚠️  Failed to format: $FILE_PATH" >&2
        exit 0  # Don't block on formatting failure
    fi
fi

exit 0
```

### Decision Control (Advanced)

For PreToolUse and PostToolUse, you can output JSON to control decisions:

```python
import json
import sys

# Block with reason
decision = {
    "decision": "block",
    "reason": "File is protected"
}
print(json.dumps(decision))
sys.exit(2)

# Or approve
decision = {
    "decision": "approve"
}
print(json.dumps(decision))
sys.exit(0)
```

## Environment Variables

Available in all hooks:

- `CLAUDE_PROJECT_DIR` - Project root directory
- `CLAUDE_TOOL_NAME` - Name of tool being called
- `CLAUDE_TOOL_INPUT_<field>` - Tool input fields (e.g., `CLAUDE_TOOL_INPUT_command`, `CLAUDE_TOOL_INPUT_file_path`)

## Common Patterns

### File Protection Pattern

```python
PROTECTED_PATTERNS = [
    '.env',
    'package-lock.json',
    '.git/',
    'node_modules/',
]

def is_protected(file_path):
    return any(pattern in file_path for pattern in PROTECTED_PATTERNS)
```

### Dangerous Command Detection

```python
import re

DANGEROUS_PATTERNS = [
    r'\brm\s+-rf\s+/',           # rm -rf /
    r'\bgit\s+push\s+--force',   # force push
    r'\bdd\s+if=',               # dd command
]

def is_dangerous(command):
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False
```

### Format After Edit Pattern

```bash
# Format TypeScript files after edit
if [[ "$CLAUDE_TOOL_NAME" =~ ^(Edit|Write)$ ]]; then
    FILE_PATH="${CLAUDE_TOOL_INPUT_file_path}"

    if [[ "$FILE_PATH" =~ \.ts$ ]]; then
        npx prettier --write "$FILE_PATH"
    fi
fi
```

### Notification Pattern

```bash
# Send notification after long operations
NTFY_URL="https://ntfy.sh/your-channel"

curl -H "Title: Claude Notification" \
     -d "Operation completed: $CLAUDE_TOOL_NAME" \
     "$NTFY_URL"
```

## Best Practices

1. **Always make scripts executable**: `chmod +x .claude/hooks/*.sh`
2. **Use `$CLAUDE_PROJECT_DIR`** for portable paths
3. **Test hooks thoroughly** before committing
4. **Provide clear error messages** via stderr
5. **Keep hooks fast** (< 1 second recommended)
6. **Use exit code 0** to approve, **exit code 2** to block
7. **Handle missing environment variables** gracefully
8. **Log to files** for debugging (not stdout/stderr)
9. **Use `.claude/settings.local.json`** for machine-specific hooks
10. **Document hook behavior** in comments

## Debugging Hooks

1. **Add debug logging**:
   ```bash
   echo "DEBUG: Tool=$CLAUDE_TOOL_NAME, File=$CLAUDE_TOOL_INPUT_file_path" >> /tmp/hook-debug.log
   ```

2. **Test hooks manually**:
   ```bash
   echo '{"tool_name": "Write", "tool_input": {"file_path": "test.md"}}' | .claude/hooks/your-hook.py
   ```

3. **Check exit codes**:
   ```bash
   .claude/hooks/your-hook.py
   echo $?  # Should be 0 or 2
   ```

## Security Considerations

- **Never log sensitive data** (passwords, tokens, etc.)
- **Validate all inputs** from environment variables
- **Use allowlists** over blocklists when possible
- **Set timeouts** on hook execution (default: 60s)
- **Avoid network calls** in critical path hooks
- **Don't trust user input** in prompts
