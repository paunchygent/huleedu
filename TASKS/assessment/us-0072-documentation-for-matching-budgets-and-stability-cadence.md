---
id: 'us-0072-documentation-for-matching-budgets-and-stability-cadence'
title: 'US-007.2: Documentation for matching budgets and stability cadence'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-28'
last_updated: '2025-11-28'
related: []
labels: []
---
# US-007.2: Documentation for matching budgets and stability cadence

## Objective

Provide clear documentation of CJ configuration parameters so developers understand how wave sizing, budgets, and stability checks interact.

## Context

Part of EPIC-007 (Developer Experience & Testing). Current documentation may imply incorrect relationships between `COMPARISONS_PER_STABILITY_CHECK_ITERATION` and wave size. This story clarifies the distinction.

## Acceptance Criteria

- [ ] `docs/services/cj-assessment-service.md` (or equivalent) is updated to:
  - Describe the responsibilities split:
    - Matching strategy: "Given essays and history, choose best wave; typical wave size = n // 2."
    - Orchestration: "Decides how often to recheck stability and when to request more waves."
  - Define:
    - `MAX_PAIRWISE_COMPARISONS` as global hard cap
    - `COMPARISONS_PER_STABILITY_CHECK_ITERATION` as cadence target, **not** wave size
- [ ] Older docs that imply "wave size must equal `COMPARISONS_PER_STABILITY_CHECK_ITERATION`" are corrected or removed
- [ ] A short reference doc exists, compliant with `docs/` rules, e.g.: `docs/reference/cj-assessment-config.md` describing:
  - All CJ-relevant settings from `Settings`
  - Expected ranges and operational impact for each (especially budgets and stability thresholds)
- [ ] All new doc filenames use kebab-case and live under allowed directories (`product/`, `services/`, `reference/`)

## Implementation Notes

Key files to create/modify:
- `docs/services/cj-assessment-service.md` (create or update)
- `docs/reference/cj-assessment-config.md` (new)
- `services/cj_assessment_service/src/config.py` (docstring updates)

## Related

- Parent epic: [EPIC-007: Developer Experience & Testing](../../../docs/product/epics/cj-developer-experience-and-testing.md)
- Related stories: US-005.2 (Stability semantics), US-007.4 (Test architecture guardrails)
