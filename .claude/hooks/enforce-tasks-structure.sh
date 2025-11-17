#!/usr/bin/env bash
# Hook: Enforce TASKS/ directory structure
# Prevents unauthorized creation of new directories in TASKS/

# Allowed top-level directories in TASKS/
ALLOWED_TASKS_DIRS=(
  "programs"
  "assessment"
  "content"
  "identity"
  "frontend"
  "infrastructure"
  "security"
  "integrations"
  "architecture"
  "archive"
)

# Helper function to check if a value is in an array
contains() {
  local needle="$1"
  shift
  local haystack=("$@")
  for item in "${haystack[@]}"; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}

# Read JSON input from stdin
INPUT=$(cat)

# Extract tool name and input using jq
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Check Write operations
if [[ "$TOOL_NAME" == "Write" ]] && [[ -n "$FILE_PATH" ]]; then
  # Check if writing to TASKS/
  if [[ "$FILE_PATH" =~ /TASKS/ ]] || [[ "$FILE_PATH" =~ ^TASKS/ ]]; then
    # Extract the path relative to TASKS/
    RELATIVE_PATH="${FILE_PATH#*/TASKS/}"

    # Skip spec files at root
    if [[ "$RELATIVE_PATH" == "_REORGANIZATION_PROPOSAL.md" ]] || \
       [[ "$RELATIVE_PATH" == "INDEX.md" ]] || \
       [[ "$RELATIVE_PATH" == "README.md" ]]; then
      exit 0
    fi

    # Split into path components
    IFS='/' read -ra PATH_PARTS <<< "$RELATIVE_PATH"

    # Check if creating a new top-level directory
    if [[ ${#PATH_PARTS[@]} -ge 1 ]]; then
      TOP_DIR="${PATH_PARTS[0]}"

      # Validate top-level directory
      if ! contains "$TOP_DIR" "${ALLOWED_TASKS_DIRS[@]}"; then
        cat >&2 << EOF
🚫 TASKS STRUCTURE VIOLATION

Cannot create new top-level directory in TASKS/:
  Directory: $TOP_DIR
  File: $FILE_PATH

Allowed top-level directories (domains):
  ${ALLOWED_TASKS_DIRS[*]}

To modify the TASKS/ structure, you must:
  1. Discuss the change with the user
  2. Update TASKS/_REORGANIZATION_PROPOSAL.md
  3. Update this enforcement hook
  4. Get explicit approval

Operation blocked.
EOF
        exit 2
      fi
    fi
  fi
fi

# Check Bash operations that might create directories
if [[ "$TOOL_NAME" == "Bash" ]] && [[ -n "$COMMAND" ]]; then
  # Check for mkdir commands in TASKS/
  if [[ "$COMMAND" =~ mkdir.*TASKS/ ]]; then
    cat >&2 << EOF
🚫 TASKS STRUCTURE VIOLATION

Direct mkdir operations in TASKS/ are blocked.
  Command: $COMMAND

The TASKS/ directory structure is locked and enforced.

If you need to create a new directory:
  1. Discuss the change with the user
  2. Update TASKS/_REORGANIZATION_PROPOSAL.md
  3. Update the enforcement hook: .claude/hooks/enforce-tasks-structure.sh
  4. Get explicit approval

Use the Write tool to create files in existing directories instead.

Operation blocked.
EOF
    exit 2
  fi

  # Check for mv/rm commands affecting TASKS/ structure directories
  if [[ "$COMMAND" =~ (mv|rm).*TASKS/(programs|assessment|content|identity|frontend|infrastructure|security|integrations|architecture|archive) ]]; then
    cat >&2 << EOF
🚫 TASKS STRUCTURE VIOLATION

Moving or removing core TASKS/ directories is blocked.
  Command: $COMMAND

The TASKS/ directory structure is locked and enforced.

If you need to modify the structure:
  1. Discuss the change with the user
  2. Update TASKS/_REORGANIZATION_PROPOSAL.md
  3. Update the enforcement hook: .claude/hooks/enforce-tasks-structure.sh
  4. Get explicit approval

Operation blocked.
EOF
    exit 2
  fi
fi

# Allow all other operations
exit 0
