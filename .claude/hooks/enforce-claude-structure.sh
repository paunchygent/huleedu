#!/usr/bin/env bash
# Hook: Enforce .claude/ directory structure
# Prevents unauthorized creation of new directories in .claude/

# Allowed directory structure in .claude/
# Top-level directories
ALLOWED_TOP_LEVEL=(
  "config"
  "agents"
  "skills"
  "commands"
  "hooks"
  "rules"
  "work"
  "archive"
  "research"
)

# Second-level directories under work/
ALLOWED_WORK_SUBDIRS=(
  "tasks"
  "session"
  "audits"
)

# Second-level directories under archive/
ALLOWED_ARCHIVE_SUBDIRS=(
  "code-reviews"
  "session-results"
  "prompts"
  "repomix"
  "task-archive"
)

# Second-level directories under research/
ALLOWED_RESEARCH_SUBDIRS=(
  "papers"
  "validation"
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

# Extract the operation details based on tool type
TOOL_NAME="${CLAUDE_TOOL_NAME:-}"
FILE_PATH="${CLAUDE_TOOL_INPUT_file_path:-}"
COMMAND="${CLAUDE_TOOL_INPUT_command:-}"

# Check Write operations
if [[ "$TOOL_NAME" == "Write" ]] && [[ -n "$FILE_PATH" ]]; then
  # Check if writing to .claude/
  if [[ "$FILE_PATH" =~ \.claude/ ]]; then
    # Extract the path relative to .claude/
    RELATIVE_PATH="${FILE_PATH#*/.claude/}"

    # Split into path components
    IFS='/' read -ra PATH_PARTS <<< "$RELATIVE_PATH"

    # Check if creating a new top-level directory
    if [[ ${#PATH_PARTS[@]} -ge 1 ]]; then
      TOP_DIR="${PATH_PARTS[0]}"

      # Validate top-level directory
      if ! contains "$TOP_DIR" "${ALLOWED_TOP_LEVEL[@]}"; then
        cat >&2 << EOF
🚫 CLAUDE STRUCTURE VIOLATION

Cannot create new top-level directory in .claude/:
  Directory: $TOP_DIR
  File: $FILE_PATH

Allowed top-level directories:
  ${ALLOWED_TOP_LEVEL[*]}

To modify the .claude/ structure, you must:
  1. Discuss the change with the user
  2. Update the structure documentation
  3. Update this enforcement hook
  4. Get explicit approval

Operation blocked.
EOF
        exit 2
      fi

      # Validate second-level directories for work/, archive/, research/
      if [[ ${#PATH_PARTS[@]} -ge 2 ]]; then
        SECOND_DIR="${PATH_PARTS[1]}"

        case "$TOP_DIR" in
          "work")
            if ! contains "$SECOND_DIR" "${ALLOWED_WORK_SUBDIRS[@]}"; then
              cat >&2 << EOF
🚫 CLAUDE STRUCTURE VIOLATION

Cannot create new subdirectory in .claude/work/:
  Directory: $SECOND_DIR
  File: $FILE_PATH

Allowed subdirectories in work/:
  ${ALLOWED_WORK_SUBDIRS[*]}

To modify the .claude/work/ structure, you must:
  1. Discuss the change with the user
  2. Update the structure documentation
  3. Update this enforcement hook
  4. Get explicit approval

Operation blocked.
EOF
              exit 2
            fi
            ;;
          "archive")
            if ! contains "$SECOND_DIR" "${ALLOWED_ARCHIVE_SUBDIRS[@]}"; then
              cat >&2 << EOF
🚫 CLAUDE STRUCTURE VIOLATION

Cannot create new subdirectory in .claude/archive/:
  Directory: $SECOND_DIR
  File: $FILE_PATH

Allowed subdirectories in archive/:
  ${ALLOWED_ARCHIVE_SUBDIRS[*]}

To modify the .claude/archive/ structure, you must:
  1. Discuss the change with the user
  2. Update the structure documentation
  3. Update this enforcement hook
  4. Get explicit approval

Operation blocked.
EOF
              exit 2
            fi
            ;;
          "research")
            if ! contains "$SECOND_DIR" "${ALLOWED_RESEARCH_SUBDIRS[@]}"; then
              cat >&2 << EOF
🚫 CLAUDE STRUCTURE VIOLATION

Cannot create new subdirectory in .claude/research/:
  Directory: $SECOND_DIR
  File: $FILE_PATH

Allowed subdirectories in research/:
  ${ALLOWED_RESEARCH_SUBDIRS[*]}

To modify the .claude/research/ structure, you must:
  1. Discuss the change with the user
  2. Update the structure documentation
  3. Update this enforcement hook
  4. Get explicit approval

Operation blocked.
EOF
              exit 2
            fi
            ;;
        esac
      fi
    fi
  fi
fi

# Check Bash operations that might create directories
if [[ "$TOOL_NAME" == "Bash" ]] && [[ -n "$COMMAND" ]]; then
  # Check for mkdir commands in .claude/
  if [[ "$COMMAND" =~ mkdir.*\.claude/ ]]; then
    # Extract the directory being created
    if [[ "$COMMAND" =~ mkdir[[:space:]]+(-p[[:space:]]+)?(.+) ]]; then
      DIR_PATH="${BASH_REMATCH[2]}"

      # Remove any trailing slashes and quotes
      DIR_PATH="${DIR_PATH%/}"
      DIR_PATH="${DIR_PATH//\"/}"

      cat >&2 << EOF
🚫 CLAUDE STRUCTURE VIOLATION

Direct mkdir operations in .claude/ are blocked.
  Command: $COMMAND
  Target: $DIR_PATH

The .claude/ directory structure is locked and enforced.

If you need to create a new directory:
  1. Discuss the change with the user
  2. Update the structure documentation
  3. Update the enforcement hook: .claude/hooks/enforce-claude-structure.sh
  4. Get explicit approval

Use the Write tool to create files in existing directories instead.

Operation blocked.
EOF
      exit 2
    fi
  fi

  # Check for mv/rm commands affecting .claude/ structure directories
  if [[ "$COMMAND" =~ (mv|rm).*\.claude/(config|agents|skills|commands|hooks|rules|work|archive|research) ]]; then
    cat >&2 << EOF
🚫 CLAUDE STRUCTURE VIOLATION

Moving or removing core .claude/ directories is blocked.
  Command: $COMMAND

The .claude/ directory structure is locked and enforced.

If you need to modify the structure:
  1. Discuss the change with the user
  2. Update the structure documentation
  3. Update the enforcement hook: .claude/hooks/enforce-claude-structure.sh
  4. Get explicit approval

Operation blocked.
EOF
    exit 2
  fi
fi

# Allow all other operations
exit 0
