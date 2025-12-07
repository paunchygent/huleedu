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

### Scope: Per-Mode Positional Fairness Diagnostics in Docker Tests

**Just completed (2025-12-07):**
- Added `pair_generation_mode` column to `ComparisonPair` for COVERAGE vs RESAMPLING tracking
- Full details in `TASKS/assessment/cj-resampling-a-b-positional-fairness.md` Section 10

**Next tasks:**
1. Update docker tests to use per-mode filtering for separate COVERAGE vs RESAMPLING fairness assertions
2. Add per-mode statistics to docker test output
3. Consider promoting helpers to repository layer if service-level metrics needed

### Key Files

| Purpose | Path |
|---------|------|
| Column definition | `services/cj_assessment_service/models_db.py:210-216` |
| Mode filtering helpers | `services/cj_assessment_service/tests/helpers/positional_fairness.py` |
| Regular-batch docker test | `tests/integration/test_cj_regular_batch_resampling_docker.py` |
| LOWER5 docker test | `tests/integration/test_cj_small_net_continuation_docker.py` |
| Task doc (full history) | `TASKS/assessment/cj-resampling-a-b-positional-fairness.md` |

### Usage Pattern

```python
from services.cj_assessment_service.tests.helpers.positional_fairness import (
    get_positional_counts_for_batch,
)

# All pairs
all_counts = await get_positional_counts_for_batch(session, cj_batch_id)

# Filter by mode
coverage = await get_positional_counts_for_batch(session, cj_batch_id, mode="coverage")
resampling = await get_positional_counts_for_batch(session, cj_batch_id, mode="resampling")
```

### Validation

```bash
# Migration tests
pdm run pytest-root services/cj_assessment_service/tests/integration/test_pair_generation_mode_migration.py -v

# Unit tests
pdm run pytest-root services/cj_assessment_service/tests/unit/test_positional_fairness_helper.py -v

# Type check
pdm run typecheck-all
```

### Before Touching Code

1. Read `TASKS/assessment/cj-resampling-a-b-positional-fairness.md` for full context
2. Read `.claude/rules/085-database-migration-standards.md` if touching schema
3. Read `.claude/rules/075-test-creation-methodology.md` for test patterns

---

## Active Blockers

None.

---

## Session End Checklist

After completing work:
1. Update the relevant TASKS/ document with implementation details
2. Update this file's NEXT SESSION INSTRUCTION for successor
3. Keep this file under 100 lines
