# .cursor/rules - FROZEN DIRECTORY

This directory is **no longer maintained** as of 2025-11-06.

## Current Status
- **Frozen**: No updates will be made to this directory
- **Legacy Reference**: Kept for historical reference only
- **File Count**: 92 .mdc files (as of freeze date)

## Source of Truth
The active source of truth for rules has been migrated to:
```
.claude/rules/
```

## Synchronization
Windsurf rules are now synced from `.claude/rules`:
```
.claude/rules/ (.mdc files)
    ↓ [pre-commit hook]
.windsurf/rules/ (.md files)
```

## Migration Details
- **Previous flow**: `.cursor/rules` → `.windsurf/rules`
- **Current flow**: `.claude/rules` → `.windsurf/rules`
- **Migration date**: 2025-11-06
- **Hook configuration**: `.pre-commit-config.yaml`
- **Sync script**: `scripts/utils/sync_rules.py`

---

For all rule updates, edits, and additions, use `.claude/rules` directory.
