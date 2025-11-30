---
id: 'eng5-boundary-test-mode-research'
title: 'ENG5 Boundary Test Mode Research'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: 'eng5'
created: '2025-11-30'
last_updated: '2025-11-30'
related: []
labels: []
---
# ENG5 Boundary Test Mode Research

## Objective

Research and design the BOUNDARY_TEST mode for the ENG5 NP runner to support controlled grade boundary comparisons.

## Context

ENG5 prompt tuning requires targeted comparisons at grade boundaries (E-/F+, D-/E+) with:
- Exact pair specification via `--boundary-pairs` CLI option
- Iteration count via `--boundary-iterations` (default: 10)
- Position swapping (each pair tested as A/B and B/A)
- Single CJ batch submission with all pre-specified comparisons

## Plan

1. Design `BoundaryPair` dataclass for pair specification
2. Design CLI integration (`--boundary-pairs`, `--boundary-iterations`)
3. Design `pre_specified_comparisons` list generation with position swapping
4. Design integration with existing content upload and Kafka flow
5. Document handler responsibilities and error handling

## Success Criteria

- [ ] CLI option design documented
- [ ] Handler flow design documented
- [ ] Integration with CJ pre-specified comparisons verified
- [ ] Ready for implementation (no assumptions remaining)

## Related

- ADR-0018: CJ Pre-Specified Comparisons
- EPIC-008 US-008.4: Controlled Grade Boundary Testing
- `scripts/cj_experiments_runners/eng5_np/handlers/anchor_align_handler.py` (pattern reference)
- `cj-pre-specified-comparisons-research` task
