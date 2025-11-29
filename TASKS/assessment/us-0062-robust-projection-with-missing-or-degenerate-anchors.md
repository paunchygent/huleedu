---
id: 'us-0062-robust-projection-with-missing-or-degenerate-anchors'
title: 'US-006.2: Robust projection with missing or degenerate anchors'
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
# US-006.2: Robust projection with missing or degenerate anchors

## Objective

Provide clear feedback when anchor configuration prevents grade projection, helping teachers understand why projections are unavailable and what corrective action to take.

## Context

Part of EPIC-006 (Grade Projection Quality & Anchors). The projection system should gracefully degrade when anchors are missing, single-grade, or insufficient, with clear logging and appropriate return values.

## Acceptance Criteria

- [ ] When no anchors are available for the batch:
  - `GradeProjector.calculate_projections` returns `projections_available = False`
  - A structured log entry explains why (no anchors / context source)
  - No `GradeProjection` rows are persisted for that batch
- [ ] When anchors exist but all share the same grade:
  - `GradeProjector.calculate_projections` returns `projections_available = False` with a warning log containing the unique grade set
- [ ] With a normal mixed-anchor scenario:
  - `projections_available = True`
  - `calibration_info` contains:
    - `grade_centers`
    - `grade_boundaries`
    - `anchor_count`
    - `anchor_grades` (set of unique anchor grades)
- [ ] Tests cover all three scenarios:
  - 0 anchors
  - Single-grade anchors
  - Multi-grade anchors
- [ ] Epic doc includes a short table: "anchor patterns -> projection behaviour"

## Implementation Notes

Key files to modify:
- `services/cj_assessment_service/src/grade_projector.py`
- `services/cj_assessment_service/src/grade_projection/projection_engine.py`

## Related

- Parent epic: [EPIC-006: Grade Projection Quality & Anchors](../../../docs/product/epics/cj-grade-projection-quality.md)
- Related stories: US-006.1 (Anchor calibration), US-006.3 (Confidence semantics)
