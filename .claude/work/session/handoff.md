# HANDOFF: Current Session Context

## Purpose

This document contains ONLY what the next developer needs to pick up work.
All completed work, patterns, and decisions live in:

- **TASKS/** – Detailed task documentation with full implementation history
- **readme-first.md** – Sprint-critical patterns, ergonomics, quick start
- **AGENTS.md** – Workflow, rules, and service conventions
- **.claude/rules/** – Implementation standards

---

## NEXT SESSION INSTRUCTION

Role: You are the lead developer and architect of HuleEdu.

### Scope: CJ Completion Semantics v2 Enforcement Complete

**Just completed (2025-12-07):**
- Enforced strict `total_budget`-only completion semantics per ADR-0020
- `completion_denominator()` now raises `RuntimeError` when `total_budget` missing/invalid
- All callers handle RuntimeError gracefully with structured logging
- Full details in `TASKS/assessment/cj-completion-semantics-v2-enforce-total-budget-and-remove-nc2-fallback.md`

**Key changes:**
- `models_db.py:315-334`: `completion_denominator()` strict budget-only
- `batch_completion_checker.py`, `batch_completion_policy.py`, `batch_monitor.py`, `workflow_continuation.py`: RuntimeError handling
- ADR-0020 status changed from "proposed" to "accepted"
- All test fixtures updated to explicitly set `total_budget`
- Fixed outbox test flakiness: added `session.expire()` before `refresh()` to handle cross-session transaction isolation

**Next tasks:**
1. Run full typecheck and test suite to verify
2. Continue with per-mode positional fairness docker tests (previous session scope)

### Key Files

| Purpose | Path |
|---------|------|
| ADR (accepted) | `docs/decisions/0020-cj-assessment-completion-semantics-v2.md` |
| Core change | `services/cj_assessment_service/models_db.py:315-334` |
| Task doc | `TASKS/assessment/cj-completion-semantics-v2-enforce-total-budget-and-remove-nc2-fallback.md` |
| Plan file | `.claude/plans/zany-sparking-kurzweil.md` |

### Validation

```bash
# Type check
pdm run typecheck-all

# Unit tests (CJ service)
pdm run pytest-root services/cj_assessment_service/tests/unit/ -v

# Specific completion semantics tests
pdm run pytest-root services/cj_assessment_service/tests/unit/test_completion_threshold.py -v
```

### Before Touching Code

1. Read ADR-0020 for budget vs coverage semantics
2. Read task doc for full implementation history

---

## Active Blockers

None.

---

## Session End Checklist

After completing work:
1. Update the relevant TASKS/ document with implementation details
2. Update this file's NEXT SESSION INSTRUCTION for successor
3. Keep this file under 100 lines
