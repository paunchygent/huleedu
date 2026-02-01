---
id: infrastructure-readme
title: Infrastructure & Orchestration Tasks README
type: doc
status: done
priority: medium
domain: infrastructure
service: ''
owner_team: infrastructure
owner: ''
program: ''
created: '2025-11-13'
last_updated: '2026-02-01'
related: []
labels: []
---
# Infrastructure & Orchestration Tasks

This directory contains task documents related to platform infrastructure, service orchestration, CI/CD, and cross-cutting operational concerns.

## What Belongs Here

Tasks that fit in this directory include:

### Infrastructure & Platform

- Docker configuration and orchestration
- Container management and optimization
- Database infrastructure patterns
- Message queue (Kafka) infrastructure
- Caching layer (Redis) configuration
- Monitoring and observability setup

### CI/CD & Automation

- Build pipelines
- Test automation frameworks
- Deployment automation
- Environment management
- Configuration validation
- Smoke testing and health checks

### Cross-Service Patterns

- Event schema governance
- Service discovery patterns
- Inter-service communication standards
- Shared configuration management
- Secrets management

### Development Tooling

- Developer workflow improvements
- Local development environment setup
- Debug and diagnostic tools
- Migration scripts and utilities

## What Does NOT Belong Here

- Service-specific implementation tasks (goes in main TASKS/)
- Feature development plans (goes in main TASKS/)
- Business logic changes (goes in main TASKS/)
- Single-service refactoring (goes in main TASKS/)

**Rule of Thumb**: If the task affects how services are built, deployed, monitored, or orchestrated together, it belongs here. If it's about what a service does (business logic), it belongs in the main TASKS/ directory.

---

## Current Infrastructure Tasks

This README intentionally does **not** list “current tasks” (it drifts quickly).
Use the query tools instead:

```bash
# In-progress infrastructure tasks
pdm run tasks --domain infrastructure --status in_progress

# Proposed infrastructure tasks (next-up)
pdm run tasks --domain infrastructure --status proposed

# Recently done infrastructure tasks
pdm run tasks --domain infrastructure --status done --updated-last-days 30
```

---

## Task Template

When creating new infrastructure tasks, use this structure:

```markdown
# TASK: [Descriptive Title]

**Status**: proposed / in_progress / blocked / done
**Priority**: LOW / MEDIUM / HIGH / CRITICAL
**Created**: YYYY-MM-DD
**Type**: Infrastructure / CI/CD / Tooling / Platform

## Purpose
[Clear statement of what problem this solves]

## Context
[Why is this needed? What's the current state?]

## Research Phase (if applicable)
[Open questions to answer before implementation]

## Design
[Proposed approach, options, tradeoffs]

## Implementation
[Specific steps to execute]

## Success Criteria
[How do we know it's done?]

## Related Documents
[Links to relevant docs, rules, services]
```

---

## Integration with Development Workflow

Infrastructure tasks often affect:

- `docker-compose.services.yml` - Service orchestration
- `pyproject.toml` - Build scripts and tooling
- `scripts/` - Automation scripts
- `.github/workflows/` - CI/CD pipelines
- `.agent/rules/` - Development standards

Always consider cross-service impact and update documentation when implementing infrastructure changes.

---

## Maintenance

This directory should be reviewed periodically to:

- Archive completed tasks (move to archive/ subfolder or add ✅ ARCHIVED status)
- Update task statuses
- Identify orphaned or outdated tasks
- Ensure new infrastructure concerns are captured

**Last Updated**: 2025-11-13
