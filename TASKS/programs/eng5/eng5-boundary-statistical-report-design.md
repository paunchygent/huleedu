---
id: eng5-boundary-statistical-report-design
title: ENG5 Boundary Statistical Report Design
type: task
status: proposed
priority: medium
domain: assessment
service: ''
owner_team: agents
owner: ''
program: eng5
created: '2025-11-30'
last_updated: '2026-02-01'
related: []
labels: []
---
# ENG5 Boundary Statistical Report Design

## Objective

Design the statistical metrics and report generation for boundary test results.

## Context

Boundary testing produces N iterations × 2 positions per grade pair. Statistical analysis needed:
- Win rate: % times higher-grade essay wins
- Mean confidence with 95% confidence interval
- Position bias: A-position win rate vs expected 50%
- Agreement rate: consistency across iterations

## Plan

1. Define `PairMetrics` dataclass with computed fields
2. Design CI calculation (bootstrap or analytical)
3. Design position bias test (binomial proportion test)
4. Design agreement rate metric (pairwise agreement?)
5. Design markdown report template
6. Consider JSON output for downstream analysis

## Success Criteria

- [ ] Metrics formulas documented
- [ ] Report template designed
- [ ] Statistical validity of CI approach verified
- [ ] Ready for implementation (no assumptions remaining)

## Related

- EPIC-008 US-008.4: Controlled Grade Boundary Testing
- `scripts/cj_experiments_runners/eng5_np/alignment_report.py` (pattern reference)
- `eng5-boundary-test-mode-research` task
