# HuleEdu Task Documentation

This directory contains planning, design, and tracking documents for significant work items across the HuleEdu platform.

## Directory Structure

```
TASKS/
├── infrastructure/          # Infrastructure, CI/CD, orchestration tasks
│   ├── README.md           # Infrastructure task guidelines
│   └── *.md                # Individual infrastructure tasks
└── *.md                    # Service-specific and feature tasks
```

## Task Organization

### Infrastructure Tasks (`infrastructure/`)

Tasks related to platform infrastructure, service orchestration, CI/CD, and cross-cutting operational concerns.

**Examples:**
- Docker configuration and orchestration
- CI/CD pipeline improvements
- Test automation frameworks
- Monitoring and observability
- Event schema governance
- Configuration validation tools

**See**: [infrastructure/README.md](./infrastructure/README.md) for details.

### Service & Feature Tasks (root level)

Tasks related to service implementation, business logic, feature development, and service-specific refactoring.

**Examples:**
- CJ assessment improvements
- Identity service implementation
- API productization
- Multi-tenancy features
- Service-specific test coverage

## Task Naming Conventions

### Numbered Tasks
Format: `NNN-descriptive-name.md`

Used for sequential, dependent tasks or milestone work.

**Example**: `002-eng5-cli-validation.md`

### Descriptive Tasks
Format: `DESCRIPTIVE_NAME_IN_CAPS.md`

Used for standalone tasks, planning documents, or major initiatives.

**Example**: `API_PRODUCTIZATION_AND_DOCS_PLAN.md`

### Prefixed Tasks
Format: `TASK-CATEGORY-description.md`

Used for categorized work items.

**Example**: `TASK-PHASE4-CODE-HARDENING.md`

## Task Statuses

Use emoji indicators in the task file:

- 🔵 **RESEARCH** - Research and planning phase
- 🟡 **BLOCKED** - Waiting on dependencies
- 🟢 **IN PROGRESS** - Active work
- ✅ **COMPLETED** - Finished
- 🔴 **PAUSED** - Temporarily suspended
- ⚫ **ARCHIVED** - Completed and archived

## Task Template

```markdown
# TASK: [Descriptive Title]

**Status**: [Status Emoji] [Status Text]
**Priority**: LOW / MEDIUM / HIGH / CRITICAL
**Created**: YYYY-MM-DD
**Assigned**: [Team/Person if applicable]
**Type**: [Feature / Refactor / Infrastructure / Research]

## Objective
[What are we trying to achieve?]

## Context
[Why is this needed? Background information]

## Prerequisites
[Dependencies, blockers, required state]

## Implementation Plan
[Detailed steps or phases]

## Success Criteria
[How do we know it's done?]

## Related Documents
[Links to relevant docs, services, rules]
```

## Integration with Documentation

Tasks complement other documentation:

- **`.claude/work/session/handoff.md`** - Current session work, immediate next steps
- **`.claude/work/session/readme-first.md`** - Architectural decisions, service status
- **`.claude/rules/`** - Implementation standards and requirements
- **`services/*/README.md`** - Service-specific patterns and guides
- **`TASKS/`** - Detailed planning and design for significant work

## Creating New Tasks

1. **Determine Category**: Infrastructure vs service/feature
2. **Choose Location**: `infrastructure/` or root level
3. **Use Template**: Follow the structure above
4. **Link Related Work**: Reference other tasks, docs, services
5. **Update Index**: Add to relevant README if creating a sequence

## Maintenance

Periodically review tasks to:
- Update statuses
- Archive completed work
- Identify stale tasks
- Ensure new work is captured
- Keep documentation links current

---

**Last Updated**: 2025-11-13
