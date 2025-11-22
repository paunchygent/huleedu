# Task Filtering Quick Reference

## Overview

Filter and query tasks by frontmatter fields using the `filter_tasks.py` script or the convenient `pdm run tasks` alias.

## Quick Start

```bash
# Using PDM alias (recommended)
pdm run tasks --priority high --status in_progress

# Direct script invocation
python scripts/task_mgmt/filter_tasks.py --priority high --status in_progress
```

## Common Use Cases

### By Priority

```bash
# High priority tasks only
pdm run tasks --priority high

# High and critical priority tasks
pdm run tasks --priority high --priority critical

# Count by priority
pdm run tasks --priority high --count-only
```

### By Status

```bash
# In-progress tasks
pdm run tasks --status in_progress

# Blocked or paused tasks requiring attention
pdm run tasks --status blocked --status paused

# Recently completed tasks
pdm run tasks --status completed --updated-last-days 7
```

### By Domain

```bash
# All assessment tasks
pdm run tasks --domain assessment

# Frontend and identity tasks
pdm run tasks --domain frontend --domain identity
```

### By Service

```bash
# Tasks for specific service
pdm run tasks --service cj_assessment_service

# Tasks for multiple services
pdm run tasks --service essay_lifecycle_service --service llm_provider_service
```

### By Date

```bash
# Created after a specific date
pdm run tasks --created-after 2025-11-01

# Updated in the last 7 days
pdm run tasks --updated-last-days 7

# Updated in the last 30 days
pdm run tasks --updated-last-days 30

# Tasks created in a date range
pdm run tasks --created-after 2025-11-01 --created-before 2025-11-15
```

### Combined Filters

```bash
# High priority in-progress assessment tasks
pdm run tasks --priority high --status in_progress --domain assessment

# Recent high-priority tasks for specific service
pdm run tasks --priority high --service cj_assessment_service --updated-last-days 7

# Blocked or paused high-priority tasks (needs attention!)
pdm run tasks --priority high --status blocked --status paused
```

## Output Formats

### Table (Default)

```bash
pdm run tasks --priority high --format table
```

Clean tabular output with columns for priority, status, domain, service, title, and updated date.

### List (Detailed)

```bash
pdm run tasks --status in_progress --format list
```

Detailed list showing all frontmatter fields including ID, paths, owner, program, etc.

### JSON (Machine Readable)

```bash
pdm run tasks --domain assessment --format json
```

JSON output suitable for scripting or further processing.

### Paths Only

```bash
pdm run tasks --status in_progress --format paths
```

Just the file paths, useful for piping to other commands:

```bash
# Edit all in-progress tasks
pdm run tasks --status in_progress --format paths | xargs code

# Count lines in high-priority tasks
pdm run tasks --priority high --format paths | xargs wc -l
```

## Sorting

```bash
# Sort by priority (critical → low)
pdm run tasks --sort priority

# Sort by most recently updated
pdm run tasks --sort updated

# Multiple sort keys (applied in order)
pdm run tasks --sort priority --sort updated

# Available sort keys: priority, created, updated, title, status, domain, service
```

## Archive Handling

By default, archived tasks are excluded. Include them with:

```bash
# Include archived tasks
pdm run tasks --include-archive --status completed

# See all archived tasks
pdm run tasks --include-archive --status archived
```

## Practical Workflows

### Morning Standup Prep

```bash
# What's in progress?
pdm run tasks --status in_progress --format list

# What's blocked?
pdm run tasks --status blocked --format list
```

### Sprint Planning

```bash
# High-priority research tasks ready to start
pdm run tasks --priority high --status research

# Count tasks by domain
pdm run tasks --domain assessment --count-only
pdm run tasks --domain infrastructure --count-only
```

### Service-Specific Work

```bash
# All tasks for CJ assessment service
pdm run tasks --service cj_assessment_service --format list

# In-progress tasks for a service
pdm run tasks --service llm_provider_service --status in_progress
```

### Recent Activity Review

```bash
# What changed this week?
pdm run tasks --updated-last-days 7 --sort updated

# Recent completions
pdm run tasks --status completed --updated-last-days 14
```

### Stale Task Detection

```bash
# In-progress tasks not updated in 30 days
pdm run tasks --status in_progress --format list | grep -E 'Updated: 2025-10-'

# Research tasks older than 60 days (may need archiving)
pdm run tasks --status research --created-before 2025-09-01
```

## Tips

1. **Combine filters freely** - All filters work together (AND logic)
2. **Use `--count-only` first** to gauge result size before full output
3. **Leverage `--format paths`** for integration with other tools
4. **Sort strategically** - Multiple sort keys are applied left to right
5. **Archive hygiene** - Exclude archives by default to focus on active work

## Script Location

- Script: `scripts/task_mgmt/filter_tasks.py`
- PDM alias: Defined in `pyproject.toml` under `[tool.pdm.scripts]`

## See Also

- `scripts/task_mgmt/new_task.py` - Create new tasks
- `scripts/task_mgmt/validate_front_matter.py` - Validate task frontmatter
- `TASKS/_REORGANIZATION_PROPOSAL.md` - Task structure specification
