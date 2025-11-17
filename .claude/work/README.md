# .claude/work/

Active work artifacts and session-specific files.

## Structure

- **tasks/** - Active task tracking and planning documents
  - Consolidated from legacy TODOs/ and tasks/ directories
  - Contains current implementation tasks and work items

- **session/** - Current session context and handoff files
  - `handoff.md` - Cross-session task context and continuity
  - `readme-first.md` - Critical session start instructions
  - `next-prompt.md` - Prepared prompt for next session (if exists)

- **audits/** - Recent compliance and structure audits
  - Documentation structure audits
  - TASKS frontmatter validation results
  - Codebase compliance checks

## Purpose

This directory contains only **active** work. Completed tasks, old session results, and historical audits should be moved to `.claude/archive/` to keep this directory focused and uncluttered.

## Maintenance

Regularly review and archive:
- Completed tasks → `archive/task-archive/`
- Old session results → `archive/session-results/`
- Historical audits → `archive/audits/` (if created)
