# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the HuleEdu platform.

## What is an ADR?

An Architecture Decision Record captures a significant architectural decision made along with its context and consequences. ADRs help us:

- Document why decisions were made
- Share context with future developers
- Track the evolution of our architecture
- Avoid repeating past discussions

## ADR Format

Each ADR follows this template:

```markdown
# ADR-XXX: Title

## Status
[Proposed | Accepted | Deprecated | Superseded by ADR-YYY]

## Context
What is the issue we're facing? Why do we need to make a decision?

## Decision
What have we decided to do?

## Consequences
### Positive
- What benefits do we gain?

### Negative
- What trade-offs are we making?

## Alternatives Considered
What other options did we evaluate and why did we reject them?

## References
Links to related documents, discussions, or code
```

## Current ADRs

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [001](001-class-management-course-skill-level.md) | Course Skill Level Architecture for Multi-Level Education | Proposed | 2025-07-22 |
| [002](002-student-record-to-user-account-linking.md) | Student Record to User Account Linking Strategy | Proposed | 2025-07-22 |

## Creating a New ADR

1. Copy the template above
2. Number it sequentially (003, 004, etc.)
3. Status starts as "Proposed"
4. After team review, update to "Accepted"
5. Update this README's index

## When to Write an ADR

Write an ADR when:
- Making a significant architectural choice
- Choosing between multiple viable options
- The decision will be hard to reverse
- Future developers will wonder "why did they do it this way?"

Don't write an ADR for:
- Implementation details that can easily change
- Obvious choices with no alternatives
- Temporary workarounds