---
id: 'cj-pre-specified-comparisons-research'
title: 'CJ Pre-Specified Comparisons Research'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-30'
last_updated: '2025-11-30'
related: []
labels: []
---
# CJ Pre-Specified Comparisons Research

## Objective

Research and design the CJ service extension to support caller-specified comparison pairs with explicit position control.

## Context

Current CJ service generates pairs internally via `pair_generation.py` and randomizes A/B positions. Controlled experiments (e.g., prompt tuning boundary tests) require:
- Exact pair specification (essay A vs essay B)
- Position control (which essay appears as A vs B)
- No internal randomization

## Plan

1. Analyze `pair_generation.generate_comparison_tasks()` flow
2. Design `PreSpecifiedComparison` model for event contract
3. Design bypass logic when `pre_specified_comparisons` provided
4. Document validation requirements (essay ID existence)
5. Consider edge cases (duplicate pairs, self-comparison)

## Success Criteria

- [ ] Design document with event contract extension
- [ ] Bypass logic design compatible with existing pair generation
- [ ] Edge case handling documented
- [ ] Ready for implementation (no assumptions remaining)

## Related

- ADR-0018: CJ Pre-Specified Comparisons
- EPIC-008 US-008.4: Controlled Grade Boundary Testing
- `services/cj_assessment_service/cj_core_logic/pair_generation.py`
- `libs/common_core/src/common_core/events/cj_assessment_events.py`
