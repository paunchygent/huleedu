# Claude Code Hooks Documentation

This directory contains hook scripts that intercept and validate operations in the Claude Code environment.

## Active Hooks

### 1. Documentation Standards Reminder (`doc-standards-reminder.sh`)

**Type**: PreToolUse (Write)
**Purpose**: Shows documentation standards when creating files in `.claude/`, `docs/`, or `TASKS/` directories.

**Behavior**:

- Triggers once per session when writing to documentation directories
- Displays the content of `.claude/rules/090-documentation-standards.md`
- Always allows the operation (exit 0)

### 2. .claude/ Structure Enforcement (`enforce-claude-structure.sh`)

**Type**: PreToolUse (Write, Bash)
**Purpose**: Enforces the canonical `.claude/` directory structure and prevents unauthorized modifications.

**Enforced Structure**:

```
.claude/
├── config/              # Configuration & settings
├── agents/              # Agent definitions
├── skills/              # Reusable skills
├── commands/            # Slash commands
├── hooks/               # Hook scripts (this directory)
├── rules/               # Development rules
├── work/                # Active work artifacts
│   ├── tasks/           # Task documentation (allows subdirs)
│   ├── session/         # handoff.md, readme-first.md
│   └── audits/          # Compliance audits
├── archive/             # Historical artifacts
│   ├── code-reviews/
│   ├── session-results/
│   ├── prompts/
│   ├── repomix/
│   └── task-archive/
└── research/            # Research & validation
    ├── papers/          # Academic papers
    └── validation/      # Technical validation
```

**Allowed Operations**:

- ✅ Creating files in any existing allowed directory
- ✅ Creating subdirectories within `work/tasks/` for task organization
- ✅ Creating subdirectories within skills for new skills (e.g., `skills/my-skill/`)
- ✅ Normal file operations outside `.claude/`

**Blocked Operations**:

- 🚫 Creating new top-level directories in `.claude/`
- 🚫 Creating new subdirectories in `work/` other than `tasks/`, `session/`, `audits/`
- 🚫 Creating new subdirectories in `archive/` other than allowed ones
- 🚫 Creating new subdirectories in `research/` other than `papers/`, `validation/`
- 🚫 Using `mkdir` commands directly in `.claude/`
- 🚫 Using `mv` or `rm` commands on core `.claude/` directories

**Behavior**:

- Validates Write operations for path compliance
- Validates Bash operations for structure-modifying commands
- Blocks non-compliant operations with clear error messages
- Exits with code 2 (block) on violations, code 0 (allow) otherwise

**Error Message Example**:

```
🚫 CLAUDE STRUCTURE VIOLATION

Cannot create new top-level directory in .claude/:
  Directory: experimental
  File: .claude/experimental/test.md

Allowed top-level directories:
  config agents skills commands hooks rules work archive research

To modify the .claude/ structure, you must:
  1. Discuss the change with the user
  2. Update the structure documentation
  3. Update this enforcement hook
  4. Get explicit approval

Operation blocked.
```

### 3. docs/ Structure Enforcement (`enforce-docs-structure.sh`)

**Type**: PreToolUse (Write, Bash)
**Purpose**: Enforces the canonical `docs/` directory structure per `DOCS_STRUCTURE_SPEC.md`.

**Allowed Top-Level Directories**:

- `overview/`, `architecture/`, `services/`, `operations/`
- `how-to/`, `reference/`, `decisions/`, `product/`, `research/`
- `_archive/` (legacy)

**Behavior**: Same as `.claude/` enforcement - blocks unauthorized directory creation.

### 4. TASKS/ Structure Enforcement (`enforce-tasks-structure.sh`)

**Type**: PreToolUse (Write, Bash)
**Purpose**: Enforces the canonical `TASKS/` directory structure per `_REORGANIZATION_PROPOSAL.md`.

**Allowed Top-Level Directories (Domains)**:

- `programs/`, `assessment/`, `content/`, `identity/`
- `frontend/`, `infrastructure/`, `security/`, `integrations/`
- `architecture/`, `archive/`

**Behavior**: Blocks creation of new domains without spec updates.

### 5. TASKS Frontmatter Validation (`validate-tasks-frontmatter.sh`)

**Type**: PreToolUse (Write)
**Purpose**: Validates TASKS file frontmatter on creation and edits.

**Validations**:

1. **Required fields**: id, title, status, priority, domain, owner_team, created, last_updated
2. **Status enum**: research, blocked, in_progress, completed, paused, archived
3. **Priority enum**: low, medium, high, critical
4. **Domain enum**: Must match allowed domains
5. **ID format**: Lowercase kebab-case (a-z, 0-9, - only)
6. **Filename match**: ID must match filename (without .md)
7. **Last updated**: Warns if not today's date on edits (doesn't block)

**Error Example**:

```
🚫 TASKS FRONTMATTER VIOLATION

Missing required fields in frontmatter:
  File: TASKS/assessment/my-task.md
  Missing: status priority domain

All task files must have these required fields:
  id title status priority domain owner_team created last_updated

Operation blocked.
```

**Warning Example**:

```
⚠️  TASKS FRONTMATTER WARNING

The last_updated field should be updated to today's date when editing:
  File: TASKS/assessment/my-task.md
  Current last_updated: 2025-11-15
  Expected: 2025-11-17

Please update the last_updated field to: 2025-11-17

Note: This is a warning. Operation will proceed, but please update the field.
```

## Testing the Enforcement Hook

### Valid Operations (Should Succeed)

```bash
# Create file in allowed location
Write: .claude/work/tasks/my-task/notes.md
Write: .claude/archive/code-reviews/review-2025-11-17.md
Write: .claude/skills/my-skill/reference.md

# Create files outside .claude/
Write: services/my_service/test.py
Write: documentation/guide.md
```

### Invalid Operations (Should Be Blocked)

```bash
# New top-level directory
Write: .claude/experimental/test.md
# ❌ Blocked: "experimental" is not in allowed top-level directories

# New work/ subdirectory
Write: .claude/work/drafts/notes.md
# ❌ Blocked: "drafts" is not allowed in work/

# Direct mkdir
Bash: mkdir -p .claude/new-directory
# ❌ Blocked: Direct mkdir in .claude/ is prohibited

# Moving core directories
Bash: mv .claude/work .claude/active
# ❌ Blocked: Moving core .claude/ directories is prohibited
```

## Modifying the Enforced Structure

If you need to add a new directory to the canonical structure:

1. **Discuss with the user**: Get explicit approval for the structural change
2. **Update the hook script**: Edit `enforce-claude-structure.sh` to add the new directory to the appropriate allow list:
   - `ALLOWED_TOP_LEVEL` for new top-level directories
   - `ALLOWED_WORK_SUBDIRS` for new `work/` subdirectories
   - `ALLOWED_ARCHIVE_SUBDIRS` for new `archive/` subdirectories
   - `ALLOWED_RESEARCH_SUBDIRS` for new `research/` subdirectories
3. **Update documentation**: Update this README and any relevant structure documentation
4. **Test the changes**: Verify the hook still works correctly

## Hook Configuration

Hooks are configured in `.claude/config/settings.local.json`:

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
          },
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/enforce-claude-structure.sh"
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/enforce-claude-structure.sh"
          }
        ]
      }
    ]
  }
}
```

## Environment Variables Available to Hooks

All hooks have access to these environment variables:

- `CLAUDE_PROJECT_DIR` - Root directory of the project
- `CLAUDE_TOOL_NAME` - Name of the tool being called (Write, Bash, Edit, etc.)
- `CLAUDE_TOOL_INPUT_*` - Tool-specific inputs (file_path, command, etc.)
- `CLAUDE_SESSION_ID` - Unique identifier for the current session

## Exit Codes

Hooks control operation flow via exit codes:

- **Exit 0**: Approve/Allow the operation
- **Exit 2**: Block the operation (stderr message shown to Claude as error)
- **Other**: Operation fails with error

## See Also

- `.claude/skills/hooks/` - Hook development skill for creating new hooks
- `.claude/config/cloud-env-instructions.md` - Environment-specific hook considerations
- `.claude/rules/090-documentation-standards.md` - Documentation standards enforced by hooks
