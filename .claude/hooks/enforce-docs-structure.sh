#!/usr/bin/env bash
# Hook: Enforce docs/ directory structure
# Prevents unauthorized creation of new directories in docs/

# Allowed top-level directories in docs/
ALLOWED_DOCS_DIRS=(
  "overview"
  "architecture"
  "services"
  "operations"
  "how-to"
  "reference"
  "decisions"
  "product"
  "research"
  "_archive"
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
  # Check if writing to docs/
  if [[ "$FILE_PATH" =~ /docs/ ]] || [[ "$FILE_PATH" =~ ^docs/ ]]; then
    # Extract the path relative to docs/
    RELATIVE_PATH="${FILE_PATH#*/docs/}"

    # Skip if writing to root level spec file
    if [[ "$RELATIVE_PATH" == "DOCS_STRUCTURE_SPEC.md" ]]; then
      exit 0
    fi

    # Split into path components
    IFS='/' read -ra PATH_PARTS <<< "$RELATIVE_PATH"

    # Check if creating a new top-level directory
    if [[ ${#PATH_PARTS[@]} -ge 1 ]]; then
      TOP_DIR="${PATH_PARTS[0]}"

      # Validate top-level directory
      if ! contains "$TOP_DIR" "${ALLOWED_DOCS_DIRS[@]}"; then
        cat >&2 << EOF
🚫 DOCS STRUCTURE VIOLATION

Cannot create new top-level directory in docs/:
  Directory: $TOP_DIR
  File: $FILE_PATH

Allowed top-level directories:
  ${ALLOWED_DOCS_DIRS[*]}

To modify the docs/ structure, you must:
  1. Discuss the change with the user
  2. Update DOCS_STRUCTURE_SPEC.md
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
  # Check for mkdir commands in docs/
  if [[ "$COMMAND" =~ mkdir.*docs/ ]]; then
    cat >&2 << EOF
🚫 DOCS STRUCTURE VIOLATION

Direct mkdir operations in docs/ are blocked.
  Command: $COMMAND

The docs/ directory structure is locked and enforced.

If you need to create a new directory:
  1. Discuss the change with the user
  2. Update DOCS_STRUCTURE_SPEC.md
  3. Update the enforcement hook: .claude/hooks/enforce-docs-structure.sh
  4. Get explicit approval

Use the Write tool to create files in existing directories instead.

Operation blocked.
EOF
    exit 2
  fi

  # Check for mv/rm commands affecting docs/ structure directories
  if [[ "$COMMAND" =~ (mv|rm).*docs/(overview|architecture|services|operations|how-to|reference|decisions|product|research) ]]; then
    cat >&2 << EOF
🚫 DOCS STRUCTURE VIOLATION

Moving or removing core docs/ directories is blocked.
  Command: $COMMAND

The docs/ directory structure is locked and enforced.

If you need to modify the structure:
  1. Discuss the change with the user
  2. Update DOCS_STRUCTURE_SPEC.md
  3. Update the enforcement hook: .claude/hooks/enforce-docs-structure.sh
  4. Get explicit approval

Operation blocked.
EOF
    exit 2
  fi
fi

# Allow all other operations
exit 0
