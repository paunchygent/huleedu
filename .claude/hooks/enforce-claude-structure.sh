#!/usr/bin/env bash
# Hook: Enforce .claude/ directory structure
# Prevents unauthorized creation of new directories in .claude/

# Allowed directory structure in .claude/
# Top-level directories (per .claude/CLAUDE_STRUCTURE_SPEC.md)
ALLOWED_TOP_LEVEL=(
  "config"           # Legacy - tool configuration
  "agents"           # Legacy - agent definitions
  "skills"           # Legacy - skill definitions
  "commands"         # Legacy - command definitions
  "hooks"            # Pre-tool-use enforcement hooks
  "rules"            # Normative coding standards
  "work"             # Session artifacts
  "archive"          # Historical work
  "research"         # Legacy - research artifacts
  "repomix_packages" # Generated repomix outputs
)

# Second-level directories under work/
ALLOWED_WORK_SUBDIRS=(
  "tasks"            # DEPRECATED - migrate to TASKS/ root directory
  "session"          # Session handoffs and state
  "reports"          # Research-diagnostic agent reports
)

# Second-level directories under archive/
# Per spec: archive/YYYY/MM/DD/session-name/ or archive/sessions/YYYY-MM/
ALLOWED_ARCHIVE_SUBDIRS=(
  "code-reviews"     # Historical code reviews
  "session-results"  # Session completion artifacts
  "sessions"         # Session-specific archives (YYYY-MM subdirs)
  "prompts"          # Historical prompts
  "repomix"          # Archived repomix outputs
  "task-archive"     # Legacy task archives
  # Also allow YYYY year directories (e.g., "2025")
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

# Read JSON input from stdin
INPUT=$(cat)

# Extract tool name and input using jq
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

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

            # Warn if creating file in deprecated .claude/work/tasks/
            if [[ "$SECOND_DIR" == "tasks" ]]; then
              cat >&2 << EOF
⚠️  DEPRECATED DIRECTORY WARNING

You are creating a file in .claude/work/tasks/ which is DEPRECATED.
  File: $FILE_PATH

Per .claude/CLAUDE_STRUCTURE_SPEC.md:
  - .claude/work/tasks/ is deprecated for task tracking
  - All tasks should be created in TASKS/ root directory with proper frontmatter
  - Use: python scripts/task_mgmt/new_task.py to create tasks

This operation is ALLOWED but discouraged.
Consider creating the task in TASKS/ instead.

EOF
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
  # Allow all operations in .claude/work/reports/ (agent output directory)
  if [[ "$COMMAND" =~ \.claude/work/reports/ ]]; then
    exit 0
  fi

  # Check for mkdir commands in .claude/
  if [[ "$COMMAND" =~ mkdir.*\.claude/ ]]; then
    # Extract the directory being created
    if [[ "$COMMAND" =~ mkdir[[:space:]]+(-p[[:space:]]+)?(.+) ]]; then
      DIR_PATH="${BASH_REMATCH[2]}"

      # Remove any trailing slashes and quotes
      DIR_PATH="${DIR_PATH%/}"
      DIR_PATH="${DIR_PATH//\"/}"

      # Extract the path relative to .claude/
      RELATIVE_PATH="${DIR_PATH#*/.claude/}"

      # Split into path components
      IFS='/' read -ra PATH_PARTS <<< "$RELATIVE_PATH"

      # Get the top-level directory being created
      if [[ ${#PATH_PARTS[@]} -ge 1 ]]; then
        TOP_DIR="${PATH_PARTS[0]}"

        # Only block if creating a NEW unauthorized top-level directory
        if ! contains "$TOP_DIR" "${ALLOWED_TOP_LEVEL[@]}"; then
          cat >&2 << EOF
🚫 CLAUDE STRUCTURE VIOLATION

Cannot create new top-level directory in .claude/:
  Command: $COMMAND
  Directory: $TOP_DIR
  Target: $DIR_PATH

Allowed top-level directories:
  ${ALLOWED_TOP_LEVEL[*]}

To modify the .claude/ structure, you must:
  1. Discuss the change with the user
  2. Update the structure documentation (.claude/CLAUDE_STRUCTURE_SPEC.md)
  3. Update this enforcement hook
  4. Get explicit approval

Operation blocked.
EOF
          exit 2
        fi

        # Allow mkdir for authorized subdirectories within allowed top-level dirs
        # This includes .claude/work/reports/, .claude/archive/2025/, etc.
      fi
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
