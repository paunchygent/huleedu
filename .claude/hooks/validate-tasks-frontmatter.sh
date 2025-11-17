#!/usr/bin/env bash
# Hook: Validate and auto-update TASKS frontmatter
# - Validates frontmatter on file creation
# - Warns about last_updated on edits
# - Enforces required fields based on task type

# Required fields for all tasks
REQUIRED_FIELDS=(
  "id"
  "title"
  "status"
  "priority"
  "domain"
  "owner_team"
  "created"
  "last_updated"
)

# Valid enum values
VALID_STATUS=("research" "blocked" "in_progress" "completed" "paused" "archived")
VALID_PRIORITY=("low" "medium" "high" "critical")
VALID_DOMAINS=("programs" "assessment" "content" "identity" "frontend" "infrastructure" "security" "integrations" "architecture")

# Helper function to check if value is in array
contains() {
  local needle="$1"
  shift
  local haystack=("$@")
  for item in "${haystack[@]}"; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}

# Extract frontmatter from content
extract_frontmatter() {
  local content="$1"
  echo "$content" | awk '/^---$/{flag=!flag; next} flag'
}

# Parse YAML field value (strips quotes)
get_yaml_value() {
  local frontmatter="$1"
  local field="$2"
  echo "$frontmatter" | grep "^${field}:" | sed "s/^${field}: *//" | sed 's/^"\(.*\)"$/\1/' | sed "s/^'\(.*\)'$/\1/"
}

# Get current date in YYYY-MM-DD format
get_today() {
  date '+%Y-%m-%d'
}

# Read JSON input from stdin
INPUT=$(cat)

# Extract tool info
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty')

# Only process Write operations on TASKS/ markdown files
if [[ "$TOOL_NAME" != "Write" ]] || [[ ! "$FILE_PATH" =~ TASKS/.*\.md$ ]]; then
  exit 0
fi

# Skip spec and meta files
BASENAME=$(basename "$FILE_PATH")
if [[ "$BASENAME" == "_REORGANIZATION_PROPOSAL.md" ]] || \
   [[ "$BASENAME" == "INDEX.md" ]] || \
   [[ "$BASENAME" == "README.md" ]] || \
   [[ "$BASENAME" == "HUB.md" ]]; then
  exit 0
fi

# Skip archive directory
if [[ "$FILE_PATH" =~ TASKS/archive/ ]]; then
  exit 0
fi

# Extract frontmatter
FRONTMATTER=$(extract_frontmatter "$CONTENT")

if [[ -z "$FRONTMATTER" ]]; then
  cat >&2 << EOF
🚫 TASKS FRONTMATTER VIOLATION

Task file is missing frontmatter:
  File: $FILE_PATH

All task files must have YAML frontmatter with required fields.

Required fields:
  ${REQUIRED_FIELDS[*]}

Example:
---
id: "my-task-id"
title: "My Task Title"
type: "task"
status: "research"
priority: "medium"
domain: "assessment"
service: ""
owner_team: "agents"
owner: ""
program: ""
created: "$(get_today)"
last_updated: "$(get_today)"
related: []
labels: []
---

Operation blocked.
EOF
  exit 2
fi

# Validate required fields
MISSING_FIELDS=()
for field in "${REQUIRED_FIELDS[@]}"; do
  value=$(get_yaml_value "$FRONTMATTER" "$field")
  if [[ -z "$value" ]]; then
    MISSING_FIELDS+=("$field")
  fi
done

if [[ ${#MISSING_FIELDS[@]} -gt 0 ]]; then
  cat >&2 << EOF
🚫 TASKS FRONTMATTER VIOLATION

Missing required fields in frontmatter:
  File: $FILE_PATH
  Missing: ${MISSING_FIELDS[*]}

All task files must have these required fields:
  ${REQUIRED_FIELDS[*]}

Operation blocked.
EOF
  exit 2
fi

# Extract field values for validation
TASK_ID=$(get_yaml_value "$FRONTMATTER" "id")
TASK_STATUS=$(get_yaml_value "$FRONTMATTER" "status")
TASK_PRIORITY=$(get_yaml_value "$FRONTMATTER" "priority")
TASK_DOMAIN=$(get_yaml_value "$FRONTMATTER" "domain")
LAST_UPDATED=$(get_yaml_value "$FRONTMATTER" "last_updated")

# Validate filename matches ID
FILENAME=$(basename "$FILE_PATH" .md)
if [[ "$TASK_ID" != "$FILENAME" ]]; then
  cat >&2 << EOF
🚫 TASKS FRONTMATTER VIOLATION

Task ID does not match filename:
  File: $FILE_PATH
  Filename: $FILENAME
  ID in frontmatter: $TASK_ID

The task ID must exactly match the filename (without .md extension).

Fix: Either rename the file or update the ID in frontmatter.

Operation blocked.
EOF
  exit 2
fi

# Validate ID format (lowercase kebab-case)
if [[ ! "$TASK_ID" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  cat >&2 << EOF
🚫 TASKS FRONTMATTER VIOLATION

Task ID has invalid format:
  File: $FILE_PATH
  ID: $TASK_ID

Task IDs must be lowercase kebab-case (a-z, 0-9, - only).

Valid examples:
  - my-task-name
  - assessment-service-implementation
  - api-v2-migration

Operation blocked.
EOF
  exit 2
fi

# Validate status enum
if ! contains "$TASK_STATUS" "${VALID_STATUS[@]}"; then
  cat >&2 << EOF
🚫 TASKS FRONTMATTER VIOLATION

Invalid status value:
  File: $FILE_PATH
  Status: $TASK_STATUS

Valid status values:
  ${VALID_STATUS[*]}

Operation blocked.
EOF
  exit 2
fi

# Validate priority enum
if ! contains "$TASK_PRIORITY" "${VALID_PRIORITY[@]}"; then
  cat >&2 << EOF
🚫 TASKS FRONTMATTER VIOLATION

Invalid priority value:
  File: $FILE_PATH
  Priority: $TASK_PRIORITY

Valid priority values:
  ${VALID_PRIORITY[*]}

Operation blocked.
EOF
  exit 2
fi

# Validate domain enum
if ! contains "$TASK_DOMAIN" "${VALID_DOMAINS[@]}"; then
  cat >&2 << EOF
🚫 TASKS FRONTMATTER VIOLATION

Invalid domain value:
  File: $FILE_PATH
  Domain: $TASK_DOMAIN

Valid domain values:
  ${VALID_DOMAINS[*]}

Operation blocked.
EOF
  exit 2
fi

# Check if file exists (edit vs. create)
if [[ -f "$FILE_PATH" ]]; then
  # File exists - this is an edit
  # Validate that last_updated is today's date
  TODAY=$(get_today)
  if [[ "$LAST_UPDATED" != "$TODAY" ]]; then
    cat >&2 << EOF
⚠️  TASKS FRONTMATTER WARNING

The last_updated field should be updated to today's date when editing:
  File: $FILE_PATH
  Current last_updated: $LAST_UPDATED
  Expected: $TODAY

Please update the last_updated field to: $TODAY

Note: This is a warning. Operation will proceed, but please update the field.
EOF
    # Warning only - don't block the operation
  fi
fi

# All validations passed
exit 0
